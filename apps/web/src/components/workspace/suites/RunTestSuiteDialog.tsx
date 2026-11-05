import { useEffect, useState } from 'react'
import { ApiError, api, type CollectionSummary } from '../../../api'
import { EnvironmentSelect } from '../../environments/EnvironmentSelect'
import { SkeletonRows } from '../../Skeleton'
import { SuiteModal, UnavailableBadge, plural } from './SuiteModal'

// Third mode of the Run dialog: pick a saved suite and run exactly its
// available test cases. The environment starts as whatever the user picked in
// the first dialog and can still be changed here. A suite with nothing
// runnable is shown but cannot be chosen.
export function RunTestSuiteDialog({
  applicationId,
  initialEnvironmentId,
  onClose,
  onRun,
}: {
  applicationId: string
  initialEnvironmentId: string | null
  onClose: () => void
  onRun: (collectionId: string, environmentId: string | null) => void
}) {
  const [suites, setSuites] = useState<CollectionSummary[] | null>(null)
  const [loadError, setLoadError] = useState<string | null>(null)
  const [selectedId, setSelectedId] = useState<string | null>(null)
  const [environmentId, setEnvironmentId] = useState<string | null>(initialEnvironmentId)

  useEffect(() => {
    let cancelled = false
    api
      .listCollections(applicationId)
      .then((data) => {
        if (cancelled) return
        setSuites(data)
        setSelectedId(data.find((s) => s.test_case_count > 0)?.id ?? null)
      })
      .catch((err) => {
        if (!cancelled) setLoadError(err instanceof ApiError ? err.message : 'Could not load test suites.')
      })
    return () => {
      cancelled = true
    }
  }, [applicationId])

  const loading = suites === null && !loadError
  const selected = suites?.find((s) => s.id === selectedId) ?? null
  const canRun = selected !== null && selected.test_case_count > 0

  return (
    <SuiteModal
      title="Run test suite"
      subtitle="Choose a suite to run all its available test cases together."
      onClose={onClose}
      maxWidth={560}
      footer={
        <>
          <span className="caption" style={{ fontSize: 12.5 }}>Unavailable test cases are skipped.</span>
          <div style={{ display: 'flex', gap: 10 }}>
            <button type="button" className="button-secondary" onClick={onClose} style={{ padding: '10px 22px', fontSize: 14 }}>
              Cancel
            </button>
            <button
              type="button"
              className="button-primary"
              aria-disabled={!canRun}
              onClick={() => canRun && selected && onRun(selected.id, environmentId)}
              style={{
                padding: '10px 22px',
                fontSize: 14,
                display: 'flex',
                alignItems: 'center',
                gap: 8,
                opacity: canRun ? 1 : 0.55,
                cursor: canRun ? 'pointer' : 'not-allowed',
              }}
            >
              {selected && selected.test_case_count > 0 ? `Run ${plural(selected.test_case_count, 'test case')}` : 'Run test cases'}
            </button>
          </div>
        </>
      }
    >
      <div style={{ padding: '4px 28px 20px', display: 'flex', flexDirection: 'column', gap: 14 }}>
        <EnvironmentSelect label="Run on environment" value={environmentId} onChange={setEnvironmentId} />
        {loadError && (
          <div role="alert" style={{ color: 'var(--danger)', fontSize: 13 }}>{loadError}</div>
        )}
        {loading ? (
          <SkeletonRows count={3} height={56} gap={8} />
        ) : suites && suites.length === 0 ? (
          <p className="caption" style={{ margin: 0 }}>
            No test suites yet. Create one from Test suites in the sidebar.
          </p>
        ) : (
          <div role="radiogroup" aria-label="Test suites" style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
            {(suites ?? []).map((suite) => {
              const runnable = suite.test_case_count > 0
              const on = suite.id === selectedId
              return (
                <button
                  key={suite.id}
                  type="button"
                  role="radio"
                  aria-checked={on}
                  aria-disabled={!runnable}
                  onClick={() => runnable && setSelectedId(suite.id)}
                  style={{
                    display: 'flex',
                    alignItems: 'center',
                    gap: 14,
                    width: '100%',
                    padding: '14px 16px',
                    borderRadius: 12,
                    border: `1px solid ${on ? 'var(--accent)' : 'var(--border-2)'}`,
                    background: on ? 'var(--accent-wash)' : 'var(--panel)',
                    cursor: runnable ? 'pointer' : 'not-allowed',
                    opacity: runnable ? 1 : 0.6,
                    textAlign: 'left',
                    fontFamily: 'inherit',
                  }}
                >
                  <span
                    aria-hidden
                    style={{
                      width: 16,
                      height: 16,
                      flex: 'none',
                      borderRadius: '50%',
                      border: on ? '5px solid var(--accent)' : '2px solid var(--fg-4)',
                      boxSizing: 'border-box',
                      background: 'var(--panel)',
                    }}
                  />
                  <span style={{ flex: 1, minWidth: 0 }}>
                    <span style={{ display: 'block', fontSize: 14.5, fontWeight: 600, color: 'var(--fg)' }}>{suite.name}</span>
                    <span className="caption" style={{ display: 'block', fontSize: 12.5, marginTop: 2 }}>
                      {runnable ? `${plural(suite.test_case_count, 'test case')} will run` : 'No test cases to run'}
                    </span>
                  </span>
                  <UnavailableBadge count={suite.unavailable_count} />
                </button>
              )
            })}
          </div>
        )}
      </div>
    </SuiteModal>
  )
}
