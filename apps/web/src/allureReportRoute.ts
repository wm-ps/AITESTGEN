// `/applications/:appId/test-runs/:runId/report` — the one stable link to a
// run's Allure report (the Runs tab button and the run-completed email).
// App.tsx renders OpenAllureReport for it, which signs in first if needed,
// then swaps in a fresh short-lived presigned URL.
//
// `/applications/:appId/test-runs/:runId` — the run-completed email's "Open
// in Vantage" link. After sign-in App.tsx loads that application and run
// through the normal org-scoped API, then opens its Runs tab on that run.

export type AllureReportRoute = { applicationId: string; testRunId: string }

const ROUTE_RE = /^\/applications\/([^/]+)\/test-runs\/([^/]+)\/report\/?$/
const RUN_ROUTE_RE = /^\/applications\/([^/]+)\/test-runs\/([^/]+)\/?$/

export function allureReportRoute(applicationId: string, testRunId: string): string {
  return `/applications/${encodeURIComponent(applicationId)}/test-runs/${encodeURIComponent(testRunId)}/report`
}

export function getAllureReportRouteFromUrl(): AllureReportRoute | null {
  return matchRoute(ROUTE_RE)
}

export function getTestRunRouteFromUrl(): AllureReportRoute | null {
  return matchRoute(RUN_ROUTE_RE)
}

function matchRoute(re: RegExp): AllureReportRoute | null {
  const match = re.exec(window.location.pathname)
  if (!match) return null
  return { applicationId: decodeURIComponent(match[1]), testRunId: decodeURIComponent(match[2]) }
}
