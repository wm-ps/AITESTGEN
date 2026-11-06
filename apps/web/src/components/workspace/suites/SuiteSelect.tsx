import { useEffect, useState } from 'react'
import { api, type CollectionSummary } from '../../../api'
import { plural } from './SuiteModal'

const ALL = '__all_test_cases__'

// The test suite picker, a twin of `EnvironmentSelect`: "All test cases" first
// (value null — everything, as before), then the application's saved suites. A
// suite with nothing runnable is listed but can't be picked. Renders nothing
// until the suites load, or when the application has none, so a screen without
// suites looks exactly as it did.
export function SuiteSelect({
  applicationId,
  value,
  onChange,
  label = 'Test suite',
}: {
  applicationId: string
  value: string | null
  onChange: (suiteId: string | null) => void
  label?: string
}) {
  const [suites, setSuites] = useState<CollectionSummary[] | null>(null)

  useEffect(() => {
    let cancelled = false
    api
      .listCollections(applicationId)
      .then((data) => {
        if (!cancelled && Array.isArray(data)) setSuites(data)
      })
      .catch(() => {
        // Without the list the caller simply targets every test case.
      })
    return () => {
      cancelled = true
    }
  }, [applicationId])

  if (!suites || suites.length === 0) return null

  return (
    <label className="field">
      <span style={{ fontSize: 12, fontWeight: 600, color: 'var(--fg-2)' }}>{label}</span>
      <select value={value ?? ALL} onChange={(e) => onChange(e.target.value === ALL ? null : e.target.value)}>
        <option value={ALL}>All test cases</option>
        {suites.map((suite) => (
          <option key={suite.id} value={suite.id} disabled={suite.test_case_count === 0 && suite.id !== value}>
            {suite.name} ({plural(suite.test_case_count, 'test case')})
          </option>
        ))}
      </select>
    </label>
  )
}
