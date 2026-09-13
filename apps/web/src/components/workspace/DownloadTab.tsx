import { useEffect, useState } from 'react'
import { FontAwesomeIcon } from '@fortawesome/react-fontawesome'
import { faChevronRight, faDownload, faFolderTree } from '@fortawesome/free-solid-svg-icons'
import { api, type TestSuiteRead } from '../../api'
import { SkeletonRows } from '../Skeleton'
import { DownloadIllustration, EmptyState } from '../EmptyState'

// Same slug rule the exporter itself uses (sanitize_slug: lowercase,
// non-alphanumerics to hyphens) — approximate here since the real slugs are
// deduped server-side; this is just for the illustrative tree below, not a
// path the download itself relies on.
function slug(name: string): string {
  return name.toLowerCase().replace(/[^a-z0-9]+/g, '-').replace(/(^-|-$)/g, '') || 'test'
}

// Folders shown before "Show N more" — keeps the card on-screen for
// applications with many journeys instead of growing the page indefinitely.
const VISIBLE_SUITES = 6

export function DownloadTab({ applicationId, applicationName }: { applicationId: string; applicationName: string }) {
  const [suites, setSuites] = useState<TestSuiteRead[] | null>(null)
  const [downloading, setDownloading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [showAllSuites, setShowAllSuites] = useState(false)
  const [expandedSuiteIds, setExpandedSuiteIds] = useState<Set<string>>(new Set())

  function toggleSuite(id: string) {
    setExpandedSuiteIds((prev) => {
      const next = new Set(prev)
      if (next.has(id)) next.delete(id)
      else next.add(id)
      return next
    })
  }

  useEffect(() => {
    let cancelled = false
    api
      .listTestSuites(applicationId)
      .then((rows) => {
        if (!cancelled) setSuites(rows)
      })
      .catch(() => {
        // best-effort — the tree preview just stays empty
      })
    return () => {
      cancelled = true
    }
  }, [applicationId])

  async function handleDownload() {
    setError(null)
    setDownloading(true)
    try {
      await api.downloadTestSuiteProject(applicationId)
    } catch {
      setError('Could not download the project. Try again.')
    } finally {
      setDownloading(false)
    }
  }

  const specCount = suites?.reduce((n, s) => n + s.test_cases.length, 0) ?? 0
  const hasSuites = suites === null || suites.length > 0

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 20 }}>
      <div style={{ display: 'flex', alignItems: 'flex-end', gap: 16, flexWrap: 'wrap' }}>
        <div style={{ minWidth: 0 }}>
          <div style={{ fontSize: 13.5, color: 'var(--fg-3)' }}>A ready-to-run Playwright repository for {applicationName}.</div>
        </div>
        <div style={{ flex: 1 }} />
        {hasSuites && (
          <button
            type="button"
            onClick={handleDownload}
            disabled={downloading}
            style={{
              display: 'inline-flex',
              alignItems: 'center',
              gap: 8,
              height: 38,
              padding: '0 20px',
              borderRadius: 8,
              background: 'var(--accent)',
              color: '#fff',
              fontSize: 13.5,
              fontWeight: 600,
              border: 'none',
              cursor: downloading ? 'not-allowed' : 'pointer',
              opacity: downloading ? 0.6 : 1,
              boxShadow: 'var(--accent-glow)',
              whiteSpace: 'nowrap',
            }}
          >
            <FontAwesomeIcon icon={faDownload} style={{ fontSize: 12 }} />
            {downloading ? 'Downloading…' : 'Download project'}
          </button>
        )}
      </div>
      {error && (
        <p role="alert" style={{ color: 'var(--bad)', fontSize: 13, margin: 0 }}>
          {error}
        </p>
      )}

      {suites !== null && suites.length === 0 ? (
        <EmptyState
          illustration={<DownloadIllustration />}
          variant="scene"
          title="No test cases generated yet"
          subtitle="Once test cases are generated, the project structure and download appear here."
        />
      ) : (
      <div
        style={{
          background: 'linear-gradient(180deg,rgba(255,255,255,0.92),rgba(255,255,255,0.74))',
          backdropFilter: 'blur(16px) saturate(1.25)',
          border: '1px solid var(--border-1)',
          borderRadius: 14,
          overflow: 'hidden',
          boxShadow: 'var(--panel-shadow)',
        }}
      >
        <div style={{ display: 'flex', alignItems: 'center', gap: 10, padding: '14px 20px', borderBottom: '1px solid var(--border-2)' }}>
          <FontAwesomeIcon icon={faFolderTree} style={{ fontSize: 12, color: "var(--accent-2)" }} />
          <span style={{ fontSize: 13.5, fontWeight: 600, color: 'var(--fg)', flex: 1 }}>Project structure</span>
          {suites && (
            <span style={{ fontFamily: 'var(--font-mono)', fontSize: 11, color: 'var(--fg-4)' }}>
              {specCount} test case{specCount === 1 ? '' : 's'} · {suites.length} journey suite{suites.length === 1 ? '' : 's'}
            </span>
          )}
        </div>
        <div style={{ padding: '20px 22px', fontFamily: 'var(--font-mono)', fontSize: 12, lineHeight: '24px', color: 'var(--fg-2)', maxHeight: 420, overflowY: 'auto' }}>
          {suites === null ? (
            <div style={{ paddingTop: 2 }}>
              <SkeletonRows count={4} height={12} gap={10} />
            </div>
          ) : (
            <>
          {slug(applicationName)}-tests/
          <br />
          <span style={{ color: 'var(--fg-6)' }}>├─</span> tests/
          {(showAllSuites ? (suites ?? []) : (suites ?? []).slice(0, VISIBLE_SUITES)).map((suite) => {
            const expanded = expandedSuiteIds.has(suite.id)
            const shownCases = expanded ? suite.test_cases : suite.test_cases.slice(0, 1)
            return (
              <span key={suite.id}>
                <br />
                <span style={{ color: 'var(--fg-6)' }}>│&nbsp;&nbsp;├─</span>{' '}
                <button
                  type="button"
                  onClick={() => toggleSuite(suite.id)}
                  disabled={suite.test_cases.length <= 1}
                  style={{
                    display: 'inline-flex',
                    alignItems: 'center',
                    gap: 4,
                    background: 'none',
                    border: 'none',
                    padding: 0,
                    font: 'inherit',
                    color: 'inherit',
                    cursor: suite.test_cases.length > 1 ? 'pointer' : 'default',
                  }}
                >
                  {suite.test_cases.length > 1 && (
                    <FontAwesomeIcon icon={faChevronRight} style={{ fontSize: 8, transition: 'transform 120ms ease', transform: expanded ? 'rotate(90deg)' : 'none' }} />
                  )}
                  {slug(suite.journey_name)}/
                </button>
                {shownCases.map((tc, i) => (
                  <span key={tc.id}>
                    <br />
                    <span style={{ color: 'var(--fg-6)' }}>│&nbsp;&nbsp;│&nbsp;&nbsp;{!expanded || i < shownCases.length - 1 ? '├─' : '└─'}</span> {slug(tc.name)}.spec.ts
                  </span>
                ))}
                {!expanded && suite.test_cases.length > 1 && (
                  <span>
                    <br />
                    <span style={{ color: 'var(--fg-6)' }}>│&nbsp;&nbsp;│&nbsp;&nbsp;└─</span>{' '}
                    <button
                      type="button"
                      onClick={() => toggleSuite(suite.id)}
                      style={{ background: 'none', border: 'none', padding: 0, font: 'inherit', color: 'var(--fg-5)', cursor: 'pointer', textDecoration: 'underline' }}
                    >
                      … {suite.test_cases.length - 1} more
                    </button>
                  </span>
                )}
              </span>
            )
          })}
          {!showAllSuites && (suites?.length ?? 0) > VISIBLE_SUITES && (
            <>
              <br />
              <span style={{ color: 'var(--fg-6)' }}>│&nbsp;&nbsp;└─</span>{' '}
              <button
                type="button"
                onClick={() => setShowAllSuites(true)}
                style={{ background: 'none', border: 'none', padding: 0, font: 'inherit', color: 'var(--accent-2)', cursor: 'pointer', fontWeight: 600 }}
              >
                Show {(suites?.length ?? 0) - VISIBLE_SUITES} more journey{(suites?.length ?? 0) - VISIBLE_SUITES === 1 ? '' : 's'}
              </button>
            </>
          )}
          <br />
          <span style={{ color: 'var(--fg-6)' }}>├─</span> fixtures/ <span style={{ color: 'var(--fg-5)' }}>— seeded auth state and test data</span>
          <br />
          <span style={{ color: 'var(--fg-6)' }}>├─</span> utils/ <span style={{ color: 'var(--fg-5)' }}>— shared helpers</span>
          <br />
          <span style={{ color: 'var(--fg-6)' }}>├─</span> playwright.config.ts
          <br />
          <span style={{ color: 'var(--fg-6)' }}>└─</span> README.md
            </>
          )}
        </div>
      </div>
      )}
    </div>
  )
}
