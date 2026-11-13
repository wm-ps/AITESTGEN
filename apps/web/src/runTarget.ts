// Which browsers and which one window size a run uses. A run on several browsers
// is still one run: each test is one row with a result per browser.
//
// The labels are what users see. The worker runs the bundled Chromium, Firefox
// and WebKit engines, so "Safari" is the WebKit engine, not macOS Safari.

export type Browser = 'chromium' | 'firefox' | 'webkit'
export type Viewport = { width: number; height: number }
export type RunTarget = { browsers: Browser[]; viewport: Viewport }

export const BROWSER_OPTIONS: { key: Browser; label: string }[] = [
  { key: 'chromium', label: 'Chrome' },
  { key: 'firefox', label: 'Firefox' },
  { key: 'webkit', label: 'Safari' },
]

// What every run used before browsers and sizes were selectable: bundled
// Chromium at Playwright's Desktop Chrome size. Tests are generated at this
// size, and it is the only one a failing test is healed at.
export const DEFAULT_VIEWPORT: Viewport = { width: 1280, height: 720 }
export const DEFAULT_TARGET: RunTarget = { browsers: ['chromium'], viewport: DEFAULT_VIEWPORT }

// Common desktop window sizes (CSS pixels). The first group is always shown;
// the second sits under "More sizes".
export const VIEWPORT_PRESETS: Viewport[] = [
  { width: 1280, height: 720 },
  { width: 1366, height: 768 },
  { width: 1536, height: 864 },
  { width: 1920, height: 1080 },
]
export const MORE_VIEWPORT_PRESETS: Viewport[] = [
  { width: 1024, height: 768 },
  { width: 1440, height: 900 },
  { width: 2560, height: 1440 },
]

// The API's bounds (domain/run_target.py) — desktop windows only.
export const VIEWPORT_LIMITS = { minWidth: 800, maxWidth: 3840, minHeight: 500, maxHeight: 2160 }

export function browserLabel(browser: string): string {
  return BROWSER_OPTIONS.find((option) => option.key === browser)?.label ?? browser
}

export function formatViewport(viewport: Viewport): string {
  return `${viewport.width} × ${viewport.height}`
}

export function sameViewport(a: Viewport, b: Viewport): boolean {
  return a.width === b.width && a.height === b.height
}

// "Chrome - 1280 × 720": what a browser chip says on hover.
export function targetLabel(browser: string, viewport: Viewport): string {
  return `${browserLabel(browser)} - ${formatViewport(viewport)}`
}

// A message when the size can't be run, null when it can. Empty custom fields
// count (they are 0).
export function viewportError(viewport: Viewport): string | null {
  const { minWidth, maxWidth, minHeight, maxHeight } = VIEWPORT_LIMITS
  if (!Number.isInteger(viewport.width) || viewport.width < minWidth || viewport.width > maxWidth) {
    return `Width must be between ${minWidth} and ${maxWidth}.`
  }
  if (!Number.isInteger(viewport.height) || viewport.height < minHeight || viewport.height > maxHeight) {
    return `Height must be between ${minHeight} and ${maxHeight}.`
  }
  return null
}

// Same browsers (in any order — the server puts Chrome first) and same size.
export function sameTarget(a: RunTarget, b: RunTarget): boolean {
  return (
    a.browsers.length === b.browsers.length &&
    a.browsers.every((browser) => b.browsers.includes(browser)) &&
    sameViewport(a.viewport, b.viewport)
  )
}

export function isDefaultTarget(target: RunTarget): boolean {
  return (
    target.browsers.length === 1 &&
    target.browsers[0] === 'chromium' &&
    sameViewport(target.viewport, DEFAULT_VIEWPORT)
  )
}

// The request fields for a target. The default sends nothing, so a plain run
// is the same request it always was.
export function targetRequest(target: RunTarget): { browsers?: Browser[]; viewport?: Viewport } {
  if (isDefaultTarget(target)) return {}
  return { browsers: target.browsers, viewport: target.viewport }
}

// A target as a saved schedule has it (the API always returns both).
export function targetFromSchedule(schedule: {
  browsers?: string[]
  viewport_width?: number
  viewport_height?: number
}): RunTarget {
  return {
    browsers: (schedule.browsers as Browser[] | undefined) ?? DEFAULT_TARGET.browsers,
    viewport: {
      width: schedule.viewport_width ?? DEFAULT_VIEWPORT.width,
      height: schedule.viewport_height ?? DEFAULT_VIEWPORT.height,
    },
  }
}
