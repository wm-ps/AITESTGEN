// Run with Node's built-in runner (no dependencies):
//   node --test packages/test_suite_assembler/tests/vantage_report_model.test.mjs
import assert from 'node:assert/strict'
import { test } from 'node:test'

import {
  buildReportModel,
  cleanSteps,
  humanizeSlug,
  journeySlugOf,
  normalizeStatus,
  summarize,
} from '../src/test_suite_assembler/vantage_report/model.mjs'

function result(overrides) {
  return {
    id: overrides.name,
    fullName: 'checkout/completes-checkout.spec.ts › ' + overrides.name,
    status: 'passed',
    start: 1000,
    stop: 2000,
    duration: 1000,
    steps: [],
    ...overrides,
  }
}

test('maps Allure statuses onto the four the report shows', () => {
  assert.equal(normalizeStatus('passed'), 'passed')
  assert.equal(normalizeStatus('failed'), 'failed')
  assert.equal(normalizeStatus('broken'), 'broken')
  assert.equal(normalizeStatus('skipped'), 'skipped')
  assert.equal(normalizeStatus('unknown'), 'broken')
  assert.equal(normalizeStatus(undefined), 'broken')
})

test('counts each status once and leaves skipped tests out of the pass rate', () => {
  const tests = ['passed', 'passed', 'passed', 'failed', 'broken', 'skipped'].map((status, i) => ({
    status,
    start: 1000 + i,
    stop: 5000 + i,
  }))
  const summary = summarize(tests)

  assert.deepEqual(summary.counts, { total: 6, passed: 3, failed: 1, broken: 1, skipped: 1 })
  assert.equal(summary.passRate, 60)
  assert.equal(summary.overall, 'failed')
  assert.equal(summary.start, 1000)
  assert.equal(summary.end, 5005)
  assert.equal(summary.duration, 4005)
})

test('overall status for clean, all-skipped and empty runs', () => {
  assert.equal(summarize([{ status: 'passed' }, { status: 'skipped' }]).overall, 'passed')
  const skipped = summarize([{ status: 'skipped' }])
  assert.equal(skipped.overall, 'skipped')
  assert.equal(skipped.passRate, null)
  const empty = summarize([])
  assert.equal(empty.overall, 'empty')
  assert.equal(empty.duration, null)
})

test('groups by the journey folder of the spec path', () => {
  assert.equal(journeySlugOf('sign-in-to-banking/logs-in.spec.ts › Logs in'), 'sign-in-to-banking')
  assert.equal(journeySlugOf('sign-in-to-banking\\logs-in.spec.ts › Logs in'), 'sign-in-to-banking')
  assert.equal(journeySlugOf('logs-in.spec.ts › Logs in'), '')
  assert.equal(humanizeSlug('sign-in-to-banking'), 'Sign in to banking')
  assert.equal(humanizeSlug(''), 'Ungrouped')

  const model = buildReportModel({
    title: 'Acme · Run #3',
    results: [
      result({ name: 'b passes' }),
      result({
        name: 'a fails',
        status: 'failed',
        error: { message: '\u001b[31mExpected\u001b[39m', trace: 'Expected\n\n    at x' },
      }),
      result({ name: 'transfers', fullName: 'transfer-funds/transfers.spec.ts › transfers' }),
    ],
  })

  assert.deepEqual(model.journeys.map((j) => j.name), ['Checkout', 'Transfer funds'])
  // Failures first inside a journey.
  assert.deepEqual(model.journeys[0].tests.map((t) => t.name), ['a fails', 'b passes'])
  assert.deepEqual(model.journeys[0].counts, { total: 2, passed: 1, failed: 1, broken: 0, skipped: 0 })
  assert.deepEqual(model.journeys[0].tests[0].error, { message: 'Expected', trace: 'at x' })
  assert.equal(model.journeys[0].tests[1].error, null)
  assert.equal(model.summary.counts.total, 3)
})

test('lifts attachments out of the step tree and drops passed hook wrappers', () => {
  const { steps, attachmentIds } = cleanSteps([
    {
      name: 'Before Hooks',
      status: 'passed',
      steps: [{ name: 'Launch browser', status: 'passed', steps: [] }],
    },
    {
      name: 'Click "Pay"',
      status: 'failed',
      duration: 120,
      message: 'locator not found',
      steps: [{ type: 'attachment', link: { id: 'shot-1' } }],
    },
    { type: 'attachment', link: { id: 'trace-1' } },
    { type: 'attachment', link: { id: 'shot-1' } },
    {
      name: 'After Hooks',
      status: 'failed',
      message: 'teardown failed',
      steps: [],
    },
  ])

  assert.deepEqual(attachmentIds, ['shot-1', 'trace-1'])
  assert.deepEqual(
    steps.map((s) => [s.name, s.status]),
    [
      ['Click "Pay"', 'failed'],
      ['After Hooks', 'failed'],
    ],
  )
  assert.deepEqual(steps[0].error, { message: 'locator not found', trace: null })
  assert.deepEqual(steps[0].steps, [])
})

test('emits only report fields — nothing about attempts or healing', () => {
  const model = buildReportModel({
    title: 'Acme',
    results: [result({ name: 'x', retries: [{}], labels: [{ name: 'host', value: 'h' }], parameters: [] })],
  })
  const testKeys = Object.keys(model.journeys[0].tests[0]).sort()
  assert.deepEqual(testKeys, [
    'attachmentIds',
    'duration',
    'error',
    'id',
    'journey',
    'journeyKey',
    'name',
    'specPath',
    'start',
    'status',
    'steps',
    'stop',
  ])
  assert.ok(!/heal|retr|attempt/i.test(JSON.stringify(model)))
})
