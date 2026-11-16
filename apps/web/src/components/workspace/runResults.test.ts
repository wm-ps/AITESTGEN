import { describe, expect, it } from 'vitest'
import type { TestResultRead, TestRunRead } from '../../api'
import {
  failsOnlyOn,
  failsOnlyOnLabel,
  groupDurationMs,
  groupResultsByTest,
  groupStatus,
  runTargetSummary,
} from './runResults'

const result = (over: Partial<TestResultRead>): TestResultRead =>
  ({
    id: 'r',
    scenario_name: 'Create a claim',
    journey_name: 'Claims',
    test_case_number: 1,
    scenario_id: 's1',
    browser: 'chromium',
    status: 'passed',
    duration_ms: 1000,
    error_message: null,
    stack_trace: null,
    blocked_reason: null,
    auto_heal_attempt_count: 0,
    manual_heal_attempt_count: 0,
    healed_test_asset_id: null,
    auto_heal_attempt_cap: 2,
    max_heal_attempts: 3,
    ...over,
  }) as TestResultRead

describe('groupResultsByTest', () => {
  it('puts one test on several browsers into one group, in the run’s browser order', () => {
    const groups = groupResultsByTest(
      [
        result({ id: 'a-ff', scenario_id: 'a', browser: 'firefox' }),
        result({ id: 'b-cr', scenario_id: 'b', browser: 'chromium' }),
        result({ id: 'a-cr', scenario_id: 'a', browser: 'chromium' }),
      ],
      ['chromium', 'firefox'],
    )

    expect(groups.map((g) => g.key)).toEqual(['a', 'b'])
    expect(groups[0].results.map((r) => r.id)).toEqual(['a-cr', 'a-ff'])
  })

  it('keeps a result whose test is gone on its own row', () => {
    const groups = groupResultsByTest(
      [result({ id: 'x', scenario_id: null }), result({ id: 'y', scenario_id: null })],
      ['chromium'],
    )
    expect(groups.map((g) => g.key)).toEqual(['x', 'y'])
  })

  it('treats an older result with no browser as Chrome', () => {
    const [group] = groupResultsByTest([result({ browser: undefined })], ['chromium'])
    expect(group.results).toHaveLength(1)
  })
})

describe('groupStatus', () => {
  it('is the result’s own status for a one-browser test', () => {
    expect(groupStatus([result({ status: 'timed_out' })])).toBe('timed_out')
  })

  it('is running while any browser is, even if another already failed', () => {
    expect(groupStatus([result({ status: 'failed' }), result({ status: 'pending' })])).toBe('pending')
  })

  it('fails if any browser failed, and passes only if all passed', () => {
    expect(groupStatus([result({ status: 'passed' }), result({ status: 'errored' })])).toBe('errored')
    expect(groupStatus([result({ status: 'passed' }), result({ status: 'passed' })])).toBe('passed')
  })

  it('reads skipped or cancelled when nothing failed', () => {
    expect(groupStatus([result({ status: 'passed' }), result({ status: 'blocked' })])).toBe('blocked')
    expect(groupStatus([result({ status: 'passed' }), result({ status: 'cancelled' })])).toBe('cancelled')
  })
})

describe('groupDurationMs', () => {
  it('adds up the browsers, and is null when none has a duration', () => {
    expect(groupDurationMs([result({ duration_ms: 1500 }), result({ duration_ms: 500 })])).toBe(2000)
    expect(groupDurationMs([result({ duration_ms: null })])).toBeNull()
  })
})

describe('failsOnlyOn', () => {
  it('names the browsers that failed while Chrome passed', () => {
    const results = [
      result({ browser: 'chromium', status: 'passed' }),
      result({ browser: 'firefox', status: 'passed' }),
      result({ browser: 'webkit', status: 'failed' }),
    ]
    expect(failsOnlyOn(results)).toEqual(['webkit'])
    expect(failsOnlyOnLabel(['webkit'])).toBe('Fails only on Safari')
  })

  it('says nothing when Chrome failed too, or did not run', () => {
    expect(
      failsOnlyOn([result({ browser: 'chromium', status: 'failed' }), result({ browser: 'webkit', status: 'failed' })]),
    ).toEqual([])
    expect(failsOnlyOn([result({ browser: 'firefox', status: 'failed' })])).toEqual([])
  })
})

describe('runTargetSummary', () => {
  const run = (over: Partial<TestRunRead>) => over as TestRunRead

  it('says nothing for the default Chrome at 1280 × 720', () => {
    expect(runTargetSummary(run({}))).toBeNull()
    expect(runTargetSummary(run({ browsers: ['chromium'], viewport_width: 1280, viewport_height: 720 }))).toBeNull()
  })

  it('says how many browsers and which size otherwise', () => {
    const summary = runTargetSummary(
      run({ browsers: ['chromium', 'firefox'], viewport_width: 1920, viewport_height: 1080 }),
    )
    expect(summary?.short).toBe('2 browsers · 1920 × 1080')
    expect(summary?.full).toBe('Chrome - 1920 × 1080, Firefox - 1920 × 1080')
  })

  it('names the browser when there is only one', () => {
    expect(runTargetSummary(run({ browsers: ['webkit'] }))?.short).toBe('Safari · 1280 × 720')
  })
})
