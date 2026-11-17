import type { TestResultRead, TestResultStatus, TestRunRead } from '../../api'
import { DEFAULT_TARGET, DEFAULT_VIEWPORT, browserLabel, formatViewport, sameViewport, type Browser, type Viewport } from '../../runTarget'

// A run on several browsers has one result per test per browser. The Runs tab
// shows one row per test, with those results as its browsers.
export type TestGroup = { key: string; results: TestResultRead[] }

const FAILED = new Set<TestResultStatus>(['failed', 'timed_out', 'errored'])
export const isFailedStatus = (status: string) => FAILED.has(status as TestResultStatus)

export const resultBrowser = (result: TestResultRead): Browser => result.browser ?? 'chromium'

export function runBrowsers(run: TestRunRead): Browser[] {
  return run.browsers ?? DEFAULT_TARGET.browsers
}

export function runViewport(run: TestRunRead): Viewport {
  return { width: run.viewport_width ?? DEFAULT_VIEWPORT.width, height: run.viewport_height ?? DEFAULT_VIEWPORT.height }
}

// Groups a run's results by test, in the order tests first appear, each group's
// results in the run's browser order. A result whose test is gone (no
// scenario_id) stands alone.
export function groupResultsByTest(results: TestResultRead[], browserOrder: Browser[]): TestGroup[] {
  const groups = new Map<string, TestResultRead[]>()
  for (const result of results) {
    const key = result.scenario_id ?? result.id
    const group = groups.get(key)
    if (group) group.push(result)
    else groups.set(key, [result])
  }
  const rank = (result: TestResultRead) => {
    const index = browserOrder.indexOf(resultBrowser(result))
    return index === -1 ? browserOrder.length : index
  }
  return [...groups].map(([key, members]) => ({ key, results: [...members].sort((a, b) => rank(a) - rank(b)) }))
}

// The one status a test's row shows: still running if any browser is, else
// failed if any failed, else skipped/cancelled, else passed.
export function groupStatus(results: TestResultRead[]): TestResultStatus {
  if (results.length === 1) return results[0].status
  const statuses = results.map((r) => r.status)
  if (statuses.includes('pending')) return 'pending'
  const failed = statuses.find((s) => FAILED.has(s))
  if (failed) return failed
  if (statuses.includes('blocked')) return 'blocked'
  if (statuses.includes('cancelled')) return 'cancelled'
  return 'passed'
}

export function groupDurationMs(results: TestResultRead[]): number | null {
  const known = results.filter((r) => r.duration_ms != null)
  return known.length > 0 ? known.reduce((sum, r) => sum + (r.duration_ms ?? 0), 0) : null
}

// The browsers that failed this test while Chrome passed it — a difference
// between browsers rather than a broken test. Empty when Chrome didn't run, or
// didn't pass.
export function failsOnlyOn(results: TestResultRead[]): Browser[] {
  const reference = results.find((r) => resultBrowser(r) === 'chromium')
  if (!reference || reference.status !== 'passed') return []
  return results.filter((r) => resultBrowser(r) !== 'chromium' && isFailedStatus(r.status)).map(resultBrowser)
}

export function failsOnlyOnLabel(browsers: Browser[]): string {
  return `Fails only on ${browsers.map(browserLabel).join(', ')}`
}

// What a run used, for its header and list row. null for the default (Chrome at
// 1280 × 720), which says nothing.
export function runTargetSummary(run: TestRunRead): { short: string; full: string } | null {
  const browsers = runBrowsers(run)
  const viewport = runViewport(run)
  if (browsers.length === 1 && browsers[0] === 'chromium' && sameViewport(viewport, DEFAULT_VIEWPORT)) return null
  const size = formatViewport(viewport)
  const browserText = browsers.length === 1 ? browserLabel(browsers[0]) : `${browsers.length} browsers`
  return {
    short: `${browserText} · ${size}`,
    full: browsers.map((b) => `${browserLabel(b)} - ${size}`).join(', '),
  }
}
