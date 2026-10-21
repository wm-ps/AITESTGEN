// Pure data shaping for the Vantage Allure report — no Allure, fs or DOM
// access, so tests/vantage_report_model.test.mjs can exercise it with plain
// objects. plugin.mjs feeds it the Allure store's test results; template.html
// renders its output.

const STATUSES = ['passed', 'failed', 'broken', 'skipped']

// Failures first inside a journey, so a reader sees what broke before
// scrolling past everything that passed.
const STATUS_ORDER = { failed: 0, broken: 1, skipped: 2, passed: 3 }

// Playwright wraps each test's fixtures in these two synthetic steps. They
// are noise in a step list unless something inside them actually failed.
const HOOK_STEP_NAMES = new Set(['Before Hooks', 'After Hooks'])

export function normalizeStatus(status) {
  return STATUSES.includes(status) ? status : 'broken'
}

// Assembled specs live at `tests/<journey-slug>/<scenario-slug>.spec.ts`, and
// allure-playwright reports that path (relative to testDir) as the part of
// `fullName` before " › ". Exported suites follow the same layout.
function specPathOf(fullName) {
  if (!fullName) return ''
  return fullName.split(' › ')[0].replace(/\\/g, '/')
}

export function journeySlugOf(fullName) {
  const parts = specPathOf(fullName).split('/')
  return parts.length > 1 ? parts[parts.length - 2] : ''
}

export function humanizeSlug(slug) {
  if (!slug) return 'Ungrouped'
  const words = slug.replace(/[-_]+/g, ' ').trim()
  return words ? words[0].toUpperCase() + words.slice(1) : 'Ungrouped'
}

const ANSI = /\u001b\[[0-9;]*[A-Za-z]/g

function stripAnsi(text) {
  return typeof text === 'string' ? text.replace(ANSI, '') : text
}

function cleanError(error) {
  if (!error || (!error.message && !error.trace)) return null
  const message = stripAnsi(error.message ?? '') || null
  let trace = stripAnsi(error.trace ?? '') || null
  // Playwright's stack repeats the whole message before the "at …" frames;
  // the report already shows the message right above it.
  if (message && trace && trace.startsWith(message)) trace = trace.slice(message.length).trim() || null
  return { message, trace }
}

// Returns { steps, attachmentIds }: attachment steps are lifted out of the
// tree (the report shows them in one gallery) and hook wrappers that passed
// are dropped. The ids keep step order so the gallery reads chronologically.
export function cleanSteps(steps, attachmentIds = []) {
  const out = []
  for (const step of steps ?? []) {
    if (step.type === 'attachment') {
      if (step.link?.id && !attachmentIds.includes(step.link.id)) attachmentIds.push(step.link.id)
      continue
    }
    const children = cleanSteps(step.steps, attachmentIds).steps
    if (HOOK_STEP_NAMES.has(step.name) && normalizeStatus(step.status) === 'passed') continue
    out.push({
      name: step.name,
      status: normalizeStatus(step.status),
      duration: step.duration ?? null,
      error: step.status === 'passed' ? null : cleanError({ message: step.message, trace: step.trace }),
      steps: children,
    })
  }
  return { steps: out, attachmentIds }
}

export function summarize(tests) {
  const counts = { total: tests.length, passed: 0, failed: 0, broken: 0, skipped: 0 }
  for (const test of tests) counts[test.status] += 1
  const executed = counts.total - counts.skipped
  const passRate = executed > 0 ? Math.round((counts.passed / executed) * 1000) / 10 : null

  const starts = tests.map((t) => t.start).filter(Number.isFinite)
  const stops = tests.map((t) => t.stop).filter(Number.isFinite)
  const start = starts.length ? Math.min(...starts) : null
  const end = stops.length ? Math.max(...stops) : null

  let overall = 'passed'
  if (counts.total === 0) overall = 'empty'
  else if (counts.failed + counts.broken > 0) overall = 'failed'
  else if (counts.passed === 0) overall = 'skipped'

  return {
    counts,
    passRate,
    overall,
    start,
    end,
    duration: start !== null && end !== null ? Math.max(0, end - start) : null,
  }
}

// `results` are plain objects shaped like Allure's TestResult (id, name,
// fullName, status, start, stop, duration, error, steps). Returns everything
// template.html renders except attachment bodies, which plugin.mjs resolves
// from `attachmentIds`.
export function buildReportModel({ title, results }) {
  const tests = results.map((tr) => {
    const { steps, attachmentIds } = cleanSteps(tr.steps)
    const slug = journeySlugOf(tr.fullName)
    return {
      id: tr.id,
      name: tr.name,
      journey: humanizeSlug(slug),
      journeyKey: slug,
      specPath: specPathOf(tr.fullName),
      status: normalizeStatus(tr.status),
      start: tr.start ?? null,
      stop: tr.stop ?? null,
      duration: tr.duration ?? null,
      error: tr.status === 'passed' ? null : cleanError(tr.error),
      steps,
      attachmentIds,
    }
  })

  const groups = new Map()
  for (const test of tests) {
    if (!groups.has(test.journeyKey)) {
      groups.set(test.journeyKey, { key: test.journeyKey, name: test.journey, tests: [] })
    }
    groups.get(test.journeyKey).tests.push(test)
  }
  const journeys = [...groups.values()]
    .map((group) => ({
      ...group,
      tests: group.tests.sort(
        (a, b) => STATUS_ORDER[a.status] - STATUS_ORDER[b.status] || a.name.localeCompare(b.name),
      ),
      counts: summarize(group.tests).counts,
    }))
    .sort((a, b) => a.name.localeCompare(b.name))

  return { title, summary: summarize(tests), journeys }
}
