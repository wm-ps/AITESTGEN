import { describe, expect, it } from 'vitest'
import {
  DEFAULT_TARGET,
  VIEWPORT_LIMITS,
  isDefaultTarget,
  targetFromSchedule,
  targetLabel,
  targetRequest,
  viewportError,
} from './runTarget'

describe('runTarget', () => {
  it('labels a target the way the browser chip says it on hover', () => {
    expect(targetLabel('chromium', { width: 1280, height: 720 })).toBe('Chrome - 1280 × 720')
    expect(targetLabel('webkit', { width: 1920, height: 1080 })).toBe('Safari - 1920 × 1080')
  })

  it('sends nothing for the default target, so a plain run is the same request it always was', () => {
    expect(isDefaultTarget(DEFAULT_TARGET)).toBe(true)
    expect(targetRequest(DEFAULT_TARGET)).toEqual({})
  })

  it('sends both fields as soon as either differs from the default', () => {
    const wider = { browsers: ['chromium' as const], viewport: { width: 1920, height: 1080 } }
    expect(targetRequest(wider)).toEqual({ browsers: ['chromium'], viewport: { width: 1920, height: 1080 } })
    const twoBrowsers = { browsers: ['chromium' as const, 'firefox' as const], viewport: DEFAULT_TARGET.viewport }
    expect(isDefaultTarget(twoBrowsers)).toBe(false)
    expect(targetRequest(twoBrowsers).browsers).toEqual(['chromium', 'firefox'])
  })

  it('accepts the size bounds and rejects anything outside them', () => {
    const { minWidth, maxWidth, minHeight, maxHeight } = VIEWPORT_LIMITS
    expect(viewportError({ width: minWidth, height: minHeight })).toBeNull()
    expect(viewportError({ width: maxWidth, height: maxHeight })).toBeNull()
    expect(viewportError({ width: minWidth - 1, height: 720 })).toMatch(/Width must be between/)
    expect(viewportError({ width: 1280, height: maxHeight + 1 })).toMatch(/Height must be between/)
  })

  it('treats empty custom fields (0) and fractions as invalid', () => {
    expect(viewportError({ width: 0, height: 0 })).not.toBeNull()
    expect(viewportError({ width: 1280.5, height: 720 })).not.toBeNull()
  })

  it('reads a saved schedule back into a target, defaulting what it lacks', () => {
    expect(targetFromSchedule({})).toEqual(DEFAULT_TARGET)
    expect(
      targetFromSchedule({ browsers: ['chromium', 'webkit'], viewport_width: 1366, viewport_height: 768 }),
    ).toEqual({ browsers: ['chromium', 'webkit'], viewport: { width: 1366, height: 768 } })
  })
})
