import { useEffect, useState } from 'react'
import { api } from '../api'
import type { AllureReportRoute } from '../allureReportRoute'
import { LoadingDots } from './LoadingDots'

// Rendered by App.tsx (signed in) for `/applications/:appId/test-runs/:runId/report`:
// asks the API for a fresh presigned URL to the run's single-file Allure
// report and replaces this page with it, so the link itself never expires.
export function OpenAllureReport({ applicationId, testRunId }: AllureReportRoute) {
  const [failed, setFailed] = useState(false)

  useEffect(() => {
    let cancelled = false
    api.getAllureReportUrl(applicationId, testRunId).then(
      ({ url }) => {
        if (!cancelled) window.location.replace(url)
      },
      () => {
        if (!cancelled) setFailed(true)
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
      {failed ? (
        <>
          <h1 style={{ fontSize: 18, fontWeight: 700, color: 'var(--fg)', margin: 0 }}>This run has no Allure report</h1>
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
