import { useEffect, useState } from 'react'
import { ApiError, api, formatTestCaseNumber, type TestSuiteRead } from '../../api'
import { LoadingDots } from '../LoadingDots'
import { useEscapeToClose } from '../../hooks/useEscapeToClose'
import { ChevronIcon } from './TestSuiteTab'

// Run Suite Flow — Run Journey(s): single-view form (no Next/Previous steps
// or nested dialogs) — reuses ScheduleDialog.tsx's overlay + card-panel
// modal shape. Selecting a Journey defaults every one of its Test Cases in;
// expanding it lets individual Test Cases be unchecked.
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
  const [suites, setSuites] = useState<TestSuiteRead[] | null>(null)
  const [loadError, setLoadError] = useState<string | null>(null)
  const [selectedTestCaseIds, setSelectedTestCaseIds] = useState<Set<string>>(new Set())
  const [expandedSuiteIds, setExpandedSuiteIds] = useState<Set<string>>(new Set())

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

  const selectedSuites = (suites ?? []).filter((s) => s.test_cases.some((tc) => selectedTestCaseIds.has(tc.id)))
  const canExecute = suiteName.trim().length > 0 && selectedTestCaseIds.size > 0

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
        onClick={(e) => e.stopPropagation()}
        className="card-panel"
        style={{
          width: '100%',
          maxWidth: 560,
          maxHeight: '82vh',
          display: 'flex',
          flexDirection: 'column',
          padding: '24px 28px',
          boxSizing: 'border-box',
        }}
      >
        <h2 style={{ fontSize: 17, fontWeight: 600, color: 'var(--ink)', margin: '0 0 18px' }}>Selective Run</h2>

        <div style={{ flex: 1, minHeight: 0, overflowY: 'auto', display: 'flex', flexDirection: 'column', gap: 14 }}>
          {loadError && (
            <div role="alert" style={{ color: 'var(--danger)', fontSize: 13 }}>
              {loadError}
            </div>
          )}

          <label className="field">
            <span className="label-required" style={{ fontSize: 12.5, fontWeight: 600, color: 'var(--ink-secondary)' }}>
              Run Name
            </span>
            <input
              required
              autoFocus
              placeholder="Checkout Regression"
              value={suiteName}
              onChange={(e) => setSuiteName(e.target.value)}
            />
          </label>

          <div>
            <span style={{ fontSize: 12.5, fontWeight: 600, color: 'var(--ink-secondary)' }}>Journeys</span>
            <div style={{ display: 'flex', flexDirection: 'column', gap: 4, marginTop: 6 }}>
              {suites === null ? (
                <LoadingDots label="Loading journeys" />
              ) : suites.length === 0 ? (
                <p className="caption">No journeys with test cases yet.</p>
              ) : (
                suites.map((suite) => {
                  const total = suite.test_cases.length
                  const selectedCount = suite.test_cases.filter((tc) => selectedTestCaseIds.has(tc.id)).length
                  const expanded = expandedSuiteIds.has(suite.id)
                  return (
                    <div key={suite.id} style={{ border: '1px solid var(--border-hairline)', borderRadius: 'var(--radius)' }}>
                      <div style={{ display: 'flex', alignItems: 'center', gap: 8, padding: '8px 10px' }}>
                        <input
                          type="checkbox"
                          checked={total > 0 && selectedCount === total}
                          ref={(el) => {
                            if (el) el.indeterminate = selectedCount > 0 && selectedCount < total
                          }}
                          onChange={() => toggleJourney(suite)}
                        />
                        <span
                          style={{ flex: 1, fontSize: 13.5, fontWeight: 600, color: 'var(--ink)', cursor: 'pointer' }}
                          onClick={() => toggleExpanded(suite.id)}
                        >
                          {suite.journey_name}
                        </span>
                        <span className="caption" style={{ fontSize: 12 }}>
                          {selectedCount}/{total} selected
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
                            gap: 6,
                            padding: '4px 10px 10px 34px',
                            borderTop: '1px solid var(--border-hairline)',
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
          </div>

          {selectedTestCaseIds.size > 0 && (
            <p className="caption" style={{ fontSize: 12.5, margin: 0 }}>
              Will run <strong>{selectedTestCaseIds.size}</strong> test case
              {selectedTestCaseIds.size === 1 ? '' : 's'} across <strong>{selectedSuites.length}</strong> journey
              {selectedSuites.length === 1 ? '' : 's'}.
            </p>
          )}
        </div>

        <div style={{ display: 'flex', gap: 10, marginTop: 18 }}>
          <button type="button" className="button-secondary" onClick={onClose} style={{ flex: 1, padding: 11, fontSize: 14 }}>
            Cancel
          </button>
          <button
            type="button"
            className="button-primary"
            disabled={!canExecute}
            onClick={() => onExecute(suiteName.trim(), [...selectedTestCaseIds])}
            style={{ flex: 1, padding: 11, fontSize: 14 }}
          >
            Execute
          </button>
        </div>
      </div>
    </div>
  )
}
