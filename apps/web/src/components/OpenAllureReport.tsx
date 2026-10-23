import { useEffect, useState } from 'react'
import { ApiError, api } from '../api'
import type { AllureReportRoute } from '../allureReportRoute'
import { LoadingDots } from './LoadingDots'

// Rendered by App.tsx (signed in) for `/applications/:appId/test-runs/:runId/report`:
// asks the API for a fresh presigned URL to the run's single-file Allure
// report and replaces this page with it, so the link itself never expires.
export function OpenAllureReport({ applicationId, testRunId }: AllureReportRoute) {
  const [failed, setFailed] = useState(false)
  // A viewer opening a shared report link — the API refuses them (403).
  const [viewOnly, setViewOnly] = useState(false)

  useEffect(() => {
    let cancelled = false
    api.getAllureReportUrl(applicationId, testRunId).then(
      ({ url }) => {
        if (!cancelled) window.location.replace(url)
      },
      (err) => {
        if (cancelled) return
        if (err instanceof ApiError && err.status === 403) setViewOnly(true)
        else setFailed(true)
      },
    )
    return () => {
      cancelled = true
    }
  }, [applicationId, testRunId])

  return (
    <main
      style={{
        height: '100vh',
        display: 'flex',
        flexDirection: 'column',
        alignItems: 'center',
        justifyContent: 'center',
        gap: 12,
        textAlign: 'center',
        padding: 24,
        boxSizing: 'border-box',
        background: 'var(--bg)',
      }}
    >
      {viewOnly ? (
        <>
          <h1 style={{ fontSize: 18, fontWeight: 700, color: 'var(--fg)', margin: 0 }}>Report not available</h1>
          <p style={{ fontSize: 14, color: 'var(--fg-4)', margin: 0, maxWidth: 380 }}>
            Reports aren&apos;t available for view-only access. Screenshots and traces are on the run in Vantage.
          </p>
          <a href="/" style={{ fontSize: 14, fontWeight: 600, color: 'var(--accent)' }}>
            Back to Vantage
          </a>
        </>
      ) : failed ? (
        <>
          <h1 style={{ fontSize: 18, fontWeight: 700, color: 'var(--fg)', margin: 0 }}>This run has no report</h1>
          <p style={{ fontSize: 14, color: 'var(--fg-4)', margin: 0, maxWidth: 380 }}>
            The report may still be generating, or this run didn&apos;t produce one.
          </p>
          <a href="/" style={{ fontSize: 14, fontWeight: 600, color: 'var(--accent)' }}>
            Back to Vantage
          </a>
        </>
      ) : (
        <span style={{ fontSize: 14, color: 'var(--fg-3)' }}>
          <LoadingDots label="Opening report" />
        </span>
      )}
    </main>
  )
}
