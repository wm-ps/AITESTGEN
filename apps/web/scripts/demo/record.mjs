// Records a single continuous walkthrough of the golden path (Sign in -> Home
// -> Connect App -> Discover Journeys -> Review Scenarios -> Generate Suite
// -> Test Suite Results -> Workspace) against the real UI, with every backend
// call mocked to return "already complete" data instantly — no real
// discovery/generation wait, sales-reel style. Captions are burned in live
// via a DOM overlay so the recording needs no separate subtitle track.
//
// Run via: synthesize-narration.ps1, then this script, then assemble.mjs.
// Output: out/clip.webm.

import { chromium } from 'playwright'
import { readFileSync, renameSync, writeFileSync } from 'node:fs'
import { fileURLToPath } from 'node:url'
import path from 'node:path'

const __dirname = path.dirname(fileURLToPath(import.meta.url))
const outDir = path.join(__dirname, 'out')

const narration = JSON.parse(readFileSync(path.join(__dirname, 'narration.json'), 'utf8'))
const durations = JSON.parse(readFileSync(path.join(outDir, 'durations.json'), 'utf8'))
const dwellMsFor = (screen) => {
  const i = narration.findIndex((n) => n.screen === screen)
  return Math.round(durations[i] * 1000)
}
const captionFor = (screen) => narration.find((n) => n.screen === screen).caption

const APP_ID = 'a1b2c3d4-0000-4000-8000-000000000001'

const USER = { name: 'Alex Morgan', email: 'alex@acme-demo.com', role: 'admin' }

const JOURNEYS = [
  { id: 'j-1', name: 'Add to Cart & Checkout', description: null, step_count: 7 },
  { id: 'j-2', name: 'Customer Sign In', description: null, step_count: 4 },
  { id: 'j-3', name: 'Search & Filter Products', description: null, step_count: 5 },
  { id: 'j-4', name: 'Update Account Profile', description: null, step_count: 4 },
]

const SCREENSHOT_SVG = encodeURIComponent(
  `<svg xmlns="http://www.w3.org/2000/svg" width="480" height="300"><rect width="480" height="300" fill="#F6F9FB"/><rect x="0" y="0" width="480" height="34" fill="#E5EAF0"/><circle cx="18" cy="17" r="5" fill="#EF4444"/><circle cx="36" cy="17" r="5" fill="#F59E0B"/><circle cx="54" cy="17" r="5" fill="#22C55E"/><circle cx="240" cy="150" r="34" fill="#DCFCE7"/><path d="M224 150l10 10 20-24" stroke="#16A34A" stroke-width="5" fill="none" stroke-linecap="round" stroke-linejoin="round"/><text x="240" y="210" font-family="Arial" font-size="16" fill="#0F172A" text-anchor="middle" font-weight="700">Order Confirmed</text><text x="240" y="232" font-family="Arial" font-size="12" fill="#64748B" text-anchor="middle">Order #WQA-48213</text></svg>`,
)

const JOURNEY_STEPS = {
  'j-1': [
    ['Home', '/', 'GET'],
    ['Product Search', '/search', 'GET'],
    ['Product Detail', '/products/wireless-headphones', 'GET'],
    ['Cart', '/cart', 'GET'],
    ['Checkout', '/checkout', 'GET'],
    ['Payment', '/checkout/payment', 'POST'],
    ['Order Confirmation', '/orders/confirmation', 'GET'],
  ].map(([stage_label, route, method], i) => ({
    step_order: i,
    stage_label,
    route,
    method,
    screenshot_url: i === 6 ? `data:image/svg+xml,${SCREENSHOT_SVG}` : null,
  })),
}

function scenario(id, journey, type, name, steps, expected_result, test_data) {
  return {
    id,
    journey_id: journey.id,
    journey_name: journey.name,
    type,
    name,
    steps,
    expected_result,
    test_data,
    test_data_complete: test_data.every((f) => !f.mandatory || f.value),
  }
}

const SCENARIOS = [
  scenario(
    's-1-happy',
    JOURNEYS[0],
    'happy',
    'Add to Cart & Checkout — Happy Path',
    [
      'Sign in as test.buyer@acme-demo.com',
      "Search for 'Wireless Headphones'",
      'Add item to cart',
      'Proceed to checkout',
      'Enter shipping address',
      'Enter payment details',
      'Confirm order',
    ],
    'Order confirmation page displays with a valid order number and the cart is emptied.',
    [
      { name: 'Email', mandatory: true, value: 'test.buyer@acme-demo.com' },
      { name: 'Card number', mandatory: true, value: '4242 4242 4242 4242' },
      { name: 'Shipping ZIP', mandatory: false, value: '94107' },
    ],
  ),
  scenario(
    's-1-negative',
    JOURNEYS[0],
    'negative',
    'Checkout — Declined Card',
    ['Add item to cart', 'Proceed to checkout', 'Enter an invalid card number', 'Submit payment'],
    'Payment is rejected and a clear "card declined" error is shown without losing the cart.',
    [{ name: 'Card number', mandatory: true, value: '4000 0000 0000 0002' }],
  ),
  scenario(
    's-1-edge',
    JOURNEYS[0],
    'edge',
    'Checkout — Empty Cart',
    ['Navigate directly to /checkout with an empty cart'],
    'User is redirected back to the cart page with a "your cart is empty" message.',
    [],
  ),
  ...JOURNEYS.slice(1).flatMap((journey, ji) => [
    scenario(`s-${ji + 2}-happy`, journey, 'happy', `${journey.name} — Happy Path`, [
      `Navigate to ${journey.name}`,
      'Complete the primary flow',
      'Verify the expected result',
    ], 'Flow completes successfully with the expected confirmation shown.', [
      { name: 'Test account', mandatory: true, value: 'test.user@acme-demo.com' },
    ]),
    scenario(`s-${ji + 2}-negative`, journey, 'negative', `${journey.name} — Invalid Input`, [
      `Navigate to ${journey.name}`,
      'Submit invalid input',
    ], 'A clear validation error is shown and no partial state is saved.', [
      { name: 'Test account', mandatory: true, value: 'test.user@acme-demo.com' },
    ]),
    scenario(`s-${ji + 2}-edge`, journey, 'edge', `${journey.name} — Boundary Condition`, [
      `Navigate to ${journey.name}`,
      'Trigger a boundary condition (max length, empty state)',
    ], 'The app handles the boundary gracefully without error.', []),
  ]),
]

const TEST_CODE = {
  's-1-happy': `import { test, expect } from '@playwright/test'

test('Add to Cart & Checkout — Happy Path', async ({ page }) => {
  await page.goto('/login')
  await page.fill('#email', 'test.buyer@acme-demo.com')
  await page.fill('#password', process.env.TEST_PASSWORD!)
  await page.click('button[type="submit"]')

  await page.fill('[data-testid="search-input"]', 'Wireless Headphones')
  await page.click('[data-testid="search-submit"]')
  await page.click('.product-card >> text=Wireless Headphones')
  await page.click('button:has-text("Add to Cart")')

  await page.click('a:has-text("Checkout")')
  await page.fill('#shipping-zip', '94107')
  await page.fill('#card-number', '4242 4242 4242 4242')
  await page.click('button:has-text("Place Order")')

  await expect(page.locator('[data-testid="order-confirmation"]')).toBeVisible()
})
`,
}
const defaultCode = (s) => TEST_CODE[s.id] ?? `import { test, expect } from '@playwright/test'

test('${s.name}', async ({ page }) => {
  await page.goto('/')
  // ${s.steps.join(' -> ')}
  await expect(page).toHaveURL(/.*/)
})
`

const SUITES = JOURNEYS.map((journey) => {
  const journeyScenarios = SCENARIOS.filter((s) => s.journey_id === journey.id)
  return {
    id: `suite-${journey.id}`,
    name: journey.name,
    journey_name: journey.name,
    status: 'complete',
    test_cases: journeyScenarios.map((s) => ({ id: s.id, name: s.name, type: s.type, code: defaultCode(s) })),
  }
})

const HOME_APP = {
  id: APP_ID,
  name: 'Acme Shop',
  url: 'https://shop.acme-demo.com',
  login_url: null,
  environment: 'staging',
  auth_method: 'standard_login',
  created_at: new Date().toISOString(),
  discovery_run_id: 'dr-1',
  discovery_status: 'complete',
  discovery_stage: 'analyzed',
  discovery_failure_reason: null,
  journey_count: JOURNEYS.length,
  scenario_count: 0,
  scenario_journeys_covered: 0,
  suite_count: 0,
  test_case_count: 0,
  suites_generating_count: 0,
}

// A single completed test run, shown on the Workspace's Runs tab — one
// failure with a visible error message is the point (tracking health, not
// just a wall of green checkmarks).
const RUN = {
  id: 'run-1',
  status: 'completed',
  trigger: 'Manual run',
  pass_rate: 10 / 12,
  total_count: 12,
  passed_count: 10,
  failed_count: 1,
  timed_out_count: 0,
  errored_count: 0,
  blocked_count: 1,
  blocked_reason: null,
  environment_snapshot: 'production',
  target_base_url_snapshot: 'https://shop.acme-demo.com',
  created_at: new Date().toISOString(),
  started_at: new Date().toISOString(),
  completed_at: new Date().toISOString(),
  results: [
    { id: 'r-1', scenario_name: 'Add to Cart & Checkout — Happy Path', status: 'passed', duration_ms: 4200, error_message: null, stack_trace: null, blocked_reason: null },
    { id: 'r-2', scenario_name: 'Checkout — Declined Card', status: 'passed', duration_ms: 2100, error_message: null, stack_trace: null, blocked_reason: null },
    {
      id: 'r-3',
      scenario_name: 'Checkout — Empty Cart',
      status: 'failed',
      duration_ms: 5300,
      error_message: 'Expected the cart page to show "your cart is empty" — the checkout page loaded instead.',
      stack_trace: null,
      blocked_reason: null,
    },
    { id: 'r-4', scenario_name: 'Customer Sign In — Happy Path', status: 'passed', duration_ms: 1800, error_message: null, stack_trace: null, blocked_reason: null },
    { id: 'r-5', scenario_name: 'Search & Filter Products — Happy Path', status: 'passed', duration_ms: 2600, error_message: null, stack_trace: null, blocked_reason: null },
  ],
}

const OVERVIEW = {
  health: { tier: 'needs_attention', headline: '1 test needs your attention' },
  total_tests: 12,
  passed: 10,
  failed: 1,
  not_run: 1,
  pass_rate: 10 / 12,
  trend: [
    { run_id: 'run-a', pass_rate: 0.6, created_at: new Date(Date.now() - 4 * 86400000).toISOString() },
    { run_id: 'run-b', pass_rate: 0.7, created_at: new Date(Date.now() - 3 * 86400000).toISOString() },
    { run_id: 'run-c', pass_rate: 0.75, created_at: new Date(Date.now() - 2 * 86400000).toISOString() },
    { run_id: 'run-d', pass_rate: 0.9, created_at: new Date(Date.now() - 1 * 86400000).toISOString() },
    { run_id: RUN.id, pass_rate: RUN.pass_rate, created_at: RUN.created_at },
  ],
  latest_run: {
    id: RUN.id,
    created_at: RUN.created_at,
    passed_count: RUN.passed_count,
    failed_count: RUN.failed_count,
    blocked_count: RUN.blocked_count,
    duration_ms: 42000,
  },
  last_discovery_started_at: new Date().toISOString(),
}

// Mocked state progresses in step with the wizard, same as the real backend
// would: journeys are already discovered from the start (discovery_status
// is 'complete' from the moment the app connects), but scenarios/suites
// only appear once their generation step is actually clicked — otherwise
// App.tsx's handleResumeApplication would see a "complete" suite the instant
// the project card is clicked and jump straight to Workspace, skipping the
// whole wizard.
let applicationCreated = false
let scenariosGenerated = false
let suiteGenerated = false

async function mockRoute(route) {
  const { pathname } = new URL(route.request().url())
  const method = route.request().method()
  const json = (body, status = 200) =>
    route.fulfill({ status, contentType: 'application/json', body: JSON.stringify(body) })

  // Always "not signed in" — the recording opens on the Sign in screen and
  // moves past it via a real /auth/login submit, so /auth/me never needs to
  // succeed.
  if (method === 'GET' && pathname === '/auth/me') return json({ detail: 'Not authenticated' }, 401)
  if (method === 'POST' && pathname === '/auth/login') return json(USER)
  if (method === 'GET' && pathname === '/home') return json(applicationCreated ? [HOME_APP] : [])
  if (method === 'POST' && pathname === '/applications') {
    applicationCreated = true
    return json(HOME_APP)
  }
  if (method === 'GET' && /^\/applications\/[^/]+$/.test(pathname)) return json(HOME_APP)
  if (method === 'GET' && /^\/applications\/[^/]+\/journeys$/.test(pathname)) return json(JOURNEYS)
  if (method === 'GET' && /^\/journeys\/[^/]+\/steps$/.test(pathname)) {
    const journeyId = pathname.split('/')[2]
    return json(JOURNEY_STEPS[journeyId] ?? [])
  }
  if (method === 'POST' && /generate-scenarios$/.test(pathname)) {
    scenariosGenerated = true
    return json({ journeys_triggered: JOURNEYS.length })
  }
  if (method === 'GET' && /^\/applications\/[^/]+\/scenarios$/.test(pathname)) {
    return json(scenariosGenerated ? SCENARIOS : [])
  }
  if (method === 'GET' && /generation-status$/.test(pathname)) return json({ available: true })
  if (method === 'POST' && /generate-suite$/.test(pathname)) {
    suiteGenerated = true
    return json({ suites_triggered: JOURNEYS.length })
  }
  if (method === 'GET' && /^\/applications\/[^/]+\/test-suites$/.test(pathname)) {
    return json(suiteGenerated ? SUITES : [])
  }
  if (method === 'GET' && /^\/applications\/[^/]+\/overview$/.test(pathname)) return json(OVERVIEW)
  if (method === 'GET' && /^\/applications\/[^/]+\/test-runs$/.test(pathname)) {
    return json({ items: [RUN], page: 1, page_size: 5, total: 1 })
  }
  if (method === 'GET' && /^\/applications\/[^/]+\/test-runs\/[^/]+$/.test(pathname)) return json(RUN)
  if (method === 'GET' && /execution-status$/.test(pathname)) return json({ available: true })

  return json({})
}

async function clearCaptions(page) {
  await page.evaluate(() => {
    document.querySelectorAll('.aitg-demo-caption').forEach((el) => el.remove())
  })
}

async function overlayCaption(page, text) {
  if (!text) return clearCaptions(page)
  await page.evaluate((caption) => {
    document.querySelectorAll('.aitg-demo-caption').forEach((el) => el.remove())
    const div = document.createElement('div')
    div.className = 'aitg-demo-caption'
    div.textContent = caption
    Object.assign(div.style, {
      position: 'fixed',
      left: '0',
      right: '0',
      bottom: '28px',
      display: 'flex',
      justifyContent: 'center',
      zIndex: '99999',
      pointerEvents: 'none',
    })
    const inner = document.createElement('div')
    inner.textContent = caption
    Object.assign(inner.style, {
      background: 'rgba(15,23,42,0.88)',
      color: '#FFFFFF',
      fontFamily: 'Arial, sans-serif',
      fontSize: '20px',
      fontWeight: '700',
      padding: '10px 22px',
      borderRadius: '10px',
      maxWidth: '85%',
      textAlign: 'center',
      boxShadow: '0 8px 24px rgba(0,0,0,0.3)',
    })
    div.textContent = ''
    div.appendChild(inner)
    document.body.appendChild(div)
  }, text)
}

// Fade to/from a solid overlay around every screen-changing click — the
// overlay `<div>` lives on `document.body`, which survives every one of
// these SPA view changes (only the React subtree under it swaps), so one
// persistent element covers the whole app for a smooth cut instead of a
// hard jump.
const FADE_MS = 220

async function fadeOut(page) {
  await page.evaluate((ms) => {
    let overlay = document.getElementById('aitg-fade')
    if (!overlay) {
      overlay = document.createElement('div')
      overlay.id = 'aitg-fade'
      Object.assign(overlay.style, {
        position: 'fixed',
        inset: '0',
        background: '#0B1220',
        opacity: '0',
        transition: `opacity ${ms}ms ease`,
        zIndex: '9999999',
        pointerEvents: 'none',
      })
      document.body.appendChild(overlay)
    }
    // eslint-disable-next-line no-unused-expressions
    overlay.offsetHeight // force layout so the transition actually animates
    overlay.style.opacity = '1'
  }, FADE_MS)
  await page.waitForTimeout(FADE_MS)
}

async function fadeIn(page) {
  await page.evaluate(() => {
    const overlay = document.getElementById('aitg-fade')
    if (overlay) overlay.style.opacity = '0'
  })
  await page.waitForTimeout(FADE_MS)
}

async function main() {
  const browser = await chromium.launch()

  // Vite's dev server compiles/transforms modules on first request — that
  // first real page load can take a couple of seconds, which used to play
  // as several seconds of blank white video with no audio before the first
  // caption ever showed. Warming it up in a throwaway (unrecorded) context
  // first means the *recorded* navigation below hits an already-compiled
  // server and is fast.
  const warmup = await browser.newContext()
  const warmupPage = await warmup.newPage()
  await warmupPage.goto('http://localhost:5173/')
  await warmupPage.getByRole('heading', { name: 'Sign in' }).waitFor()
  await warmup.close()

  // Playwright's video recorder captures at the CSS viewport size regardless
  // of deviceScaleFactor (it does NOT render at the scaled device-pixel
  // buffer) — a deviceScaleFactor bump just gets letterboxed, not upscaled.
  // Rendering natively at a bigger viewport (matched exactly by recordVideo
  // size, so there's no letterbox/scale mismatch either) is what actually
  // produces a crisp capture. Sized closer to the app's own centered
  // max-width layouts (--content-max: 1180px etc.) than a full 1920px —
  // otherwise those screens sit in a sea of side margin.
  const context = await browser.newContext({
    viewport: { width: 1366, height: 768 },
    recordVideo: { dir: outDir, size: { width: 1366, height: 768 } },
  })
  const page = await context.newPage()
  await page.route('http://localhost:8000/**', mockRoute)

  // Voice/screen sync bug: the audio track used to be laid out assuming
  // each scene starts exactly when the previous one's dwell time ends —
  // but real clicks/fills/waitFor()s/fades between scenes cost real
  // wall-clock time the dwell math never accounted for, so drift
  // compounded scene over scene. Recording the *actual* timestamp each
  // caption appears (relative to recording start) and having assemble.mjs
  // place each narration clip there directly removes the drift at the
  // root instead of re-guessing better dwell padding.
  const t0 = Date.now()
  const timeline = []
  function markBeat(screen) {
    timeline.push({ screen, atMs: Date.now() - t0 })
  }

  // 1. Intro — the hook is about the product, not about the act of signing
  // in; the sign-in screen just happens to be the fancy backdrop while it
  // plays, then a real submit moves the story forward. Problem statement
  // first, then a distinct beat naming the product — both hold on the same
  // screen, no navigation between them, so no fade needed here. Caption/
  // audio starts the instant the screen is ready — filling the form
  // happens after, not before, so it never pads out the lead-in silence.
  await page.goto('http://localhost:5173/')
  await page.getByRole('heading', { name: 'Sign in' }).waitFor()
  markBeat('intro')
  await overlayCaption(page, captionFor('intro'))
  await page.getByLabel('Work email').fill('alex@acme-demo.com')
  await page.getByRole('textbox', { name: 'Password' }).fill('DemoPass123!')
  await page.waitForTimeout(dwellMsFor('intro'))
  markBeat('introducing')
  await overlayCaption(page, captionFor('introducing'))
  await page.waitForTimeout(dwellMsFor('introducing'))
  await fadeOut(page)
  await page.getByRole('button', { name: 'Sign in' }).click()

  // 2. Home (empty state — nothing connected yet)
  await page.getByText('No projects yet').waitFor()
  await fadeIn(page)
  markBeat('home')
  await overlayCaption(page, captionFor('home'))
  await page.waitForTimeout(dwellMsFor('home'))

  // 3. Connect App
  await fadeOut(page)
  await page.getByRole('button', { name: '+ Create New Project' }).click()
  await page.getByText('Connect to your live application').waitFor()
  await fadeIn(page)
  await page.getByLabel('Application name', { exact: true }).fill('Acme Shop')
  await page.getByLabel('Application URL', { exact: true }).fill('https://shop.acme-demo.com')
  await page.getByLabel('Username', { exact: true }).fill('qa_tester')
  await page.getByLabel('Password', { exact: true }).fill('DemoPass123!')
  markBeat('connect-app')
  await overlayCaption(page, captionFor('connect-app'))
  await page.waitForTimeout(dwellMsFor('connect-app'))
  await fadeOut(page)
  await page.getByRole('button', { name: 'Connect Application →' }).click()

  // Back on Home — the new project card is now there. A brief beat (not an
  // instant fade-in-then-out blink), but short — it has no narration of its
  // own, so it stays transition-scale rather than a held silent gap.
  await page.getByText('Acme Shop').waitFor()
  await fadeIn(page)
  await page.waitForTimeout(600)
  await fadeOut(page)
  await page.getByText('Acme Shop').click()

  // 4. Discover Journeys (default-selects the first journey already)
  await page.getByRole('heading', { name: 'Discover Journeys' }).waitFor()
  await page.getByText('Discovered flow').waitFor()
  await fadeIn(page)
  markBeat('discover')
  await overlayCaption(page, captionFor('discover'))
  await page.waitForTimeout(dwellMsFor('discover'))
  await fadeOut(page)
  await page.getByRole('button', { name: 'Continue to Scenarios →' }).click()

  // 5. Review Scenarios (default-selects the first scenario already)
  await page.getByRole('heading', { name: 'Review Scenarios' }).waitFor()
  await page.getByText('Test steps').waitFor()
  await fadeIn(page)
  markBeat('review-scenarios')
  await overlayCaption(page, captionFor('review-scenarios'))
  await page.waitForTimeout(dwellMsFor('review-scenarios'))
  await fadeOut(page)
  await page.getByRole('button', { name: 'Generate Test Suite →' }).click()

  // 6. Generate Suite
  await page.getByText('Configure this suite').waitFor()
  await fadeIn(page)
  await page.getByLabel('Target environment').selectOption('production')
  markBeat('generate-suite')
  await overlayCaption(page, captionFor('generate-suite'))
  await page.waitForTimeout(dwellMsFor('generate-suite'))
  await fadeOut(page)
  await page.getByRole('button', { name: 'Generate Test Suite →' }).click()

  // 7. Test Suite Results
  await page.getByText('Test Suites Generated').waitFor()
  await fadeIn(page)
  await page.getByRole('button', { name: 'View Tests' }).click()
  await page.getByText('add-to-cart-checkout.spec.ts').click()
  await page.getByRole('button', { name: 'Code' }).first().click()
  await page.getByText('async ({ page }) =>').waitFor()
  markBeat('test-suite-results')
  await overlayCaption(page, captionFor('test-suite-results'))
  await page.waitForTimeout(dwellMsFor('test-suite-results'))
  await page.getByLabel('Close').click()

  // 8. Health — application health tracked over time. Its own held beat
  // (not rushed straight into the run list) so it doesn't read as a blink
  // between screens.
  await fadeOut(page)
  await page.getByRole('button', { name: 'View Executions' }).click()
  await page.getByRole('tab', { name: 'Overview' }).waitFor()
  await page.getByRole('tab', { name: 'Overview' }).click()
  await page.getByText('1 test needs your attention').waitFor()
  await fadeIn(page)
  markBeat('health')
  await overlayCaption(page, captionFor('health'))
  await page.waitForTimeout(dwellMsFor('health'))

  // 9. Issues — a quick, transition-scale look at the Runs list (no
  // narration of its own, so it stays brief rather than a held silent
  // gap) before jumping into the one failing run's detail.
  await fadeOut(page)
  await page.getByRole('tab', { name: 'Runs' }).click()
  await page.getByText('Manual run').waitFor()
  await fadeIn(page)
  await page.waitForTimeout(600)
  await fadeOut(page)
  await page.getByText('Manual run').click()
  await page.getByText('your cart is empty').waitFor()
  await fadeIn(page)
  markBeat('issues')
  await overlayCaption(page, captionFor('issues'))
  await page.waitForTimeout(dwellMsFor('issues'))

  // 10. Closing — no card, no caption, just the line landing over the real
  // product one last time.
  await clearCaptions(page)
  markBeat('closing')
  await page.waitForTimeout(dwellMsFor('closing'))

  await context.close()
  const videoPath = await page.video().path()
  await browser.close()
  renameSync(videoPath, path.join(outDir, 'clip.webm'))
  writeFileSync(path.join(outDir, 'timeline.json'), JSON.stringify(timeline))
}

main().catch((err) => {
  console.error(err)
  process.exit(1)
})
