// `/applications/:appId/test-runs/:runId/report` — the one stable link to a
// run's Allure report (Runs tab button now, the run-report email later).
// App.tsx renders OpenAllureReport for it, which signs in first if needed,
// then swaps in a fresh short-lived presigned URL.

export type AllureReportRoute = { applicationId: string; testRunId: string }

const ROUTE_RE = /^\/applications\/([^/]+)\/test-runs\/([^/]+)\/report\/?$/

export function allureReportRoute(applicationId: string, testRunId: string): string {
  return `/applications/${encodeURIComponent(applicationId)}/test-runs/${encodeURIComponent(testRunId)}/report`
}

export function getAllureReportRouteFromUrl(): AllureReportRoute | null {
  const match = ROUTE_RE.exec(window.location.pathname)
  if (!match) return null
  return { applicationId: decodeURIComponent(match[1]), testRunId: decodeURIComponent(match[2]) }
}
