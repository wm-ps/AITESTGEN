import type { components } from './api-types.gen'

// `role` isn't in api-types.gen.ts yet (that file is generated from a
// running API's OpenAPI schema, regenerate via `npm run generate:api-types`)
// — added by hand for now rather than blocking this on a live server.
export type UserRead = components['schemas']['UserRead'] & { role: 'admin' | 'member' }
export type LoginRequest = components['schemas']['LoginRequest']
export type InviteCreate = { email: string; role: 'admin' | 'member' }
export type InviteRead = { id: string; email: string; role: 'admin' | 'member'; expires_at: string }
export type AcceptInviteRequest = { token: string; name: string; password: string }
export type ForgotPasswordRequest = { email: string }
export type ResetPasswordTarget = { name: string; email: string }
export type ResetPasswordRequest = { token: string; password: string }
export type ApplicationCreate = components['schemas']['ApplicationCreate']
export type ApplicationRead = components['schemas']['ApplicationRead']
// Not in api-types.gen.ts yet (backend schema is new, regenerate via
// `npm run generate:api-types` once the API is running) — added by hand.
export type HomeApplicationRead = ApplicationRead & {
  journey_count: number
  scenario_count: number
  scenario_journeys_covered: number
  suite_count: number
  test_case_count: number
  suites_generating_count: number
  last_test_run_status: 'pending' | 'running' | 'completed' | 'blocked' | null
  last_test_run_created_at: string | null
  last_test_run_pass_rate: number | null
  last_test_run_health: HealthRead
  test_run_count: number
  recent_pass_rates: (number | null)[]
  last_discovery_started_at: string | null
  last_test_run_passed_count: number | null
  last_test_run_failed_count: number | null
}
// Global overview's org-wide "Avg run duration"/"Self-healed locators"
// sidebar cards — not per-application, so a separate endpoint from /home.
export type OverviewStatsRead = {
  avg_run_duration_ms: number | null
  run_count: number
  self_healed_count: number
  self_healed_since: string
}
export type JourneyRead = components['schemas']['JourneyRead']
export type JourneyStepRead = components['schemas']['JourneyStepRead']
// `test_case_number` isn't in api-types.gen.ts yet (regenerate via `npm run
// generate:api-types` once the API is running) — added by hand. Test Case
// Number feature: persistent, sequential, per-Application display id.
export type ScenarioRead = components['schemas']['ScenarioRead'] & { test_case_number: number }
// `description` isn't in api-types.gen.ts yet (regenerate via `npm run
// generate:api-types` once the API is running) — added by hand.
// 'discovery' (normal Discovery -> Journey -> Scenario pipeline) or 'nl'
// (created via live browser exploration from a plain-English request).
// Mirrors `Scenario.source`/`TestCaseRead.source` (apps/api/src/api/main.py).
export type TestCaseSource = 'discovery' | 'nl'
export type TestCaseRead = components['schemas']['TestCaseRead'] & {
  description: string
  source: TestCaseSource
  // Test Case Number feature — see ScenarioRead's own comment.
  test_case_number: number
  journey_name: string
}
// Test Case Number feature: `TC-001`, zero-padded to 3 digits. `null`/
// `undefined` only for a synthesized/placeholder row that has no real
// Scenario behind it yet.
export function formatTestCaseNumber(n: number | null | undefined): string {
  return n == null ? '' : `TC-${String(n).padStart(3, '0')}`
}
// `status` isn't in api-types.gen.ts yet (regenerate via `npm run
// generate:api-types` once the API is running) — added by hand.
export type TestSuiteStatus = 'generating' | 'complete' | 'incomplete' | 'terminated'
export type TestSuiteRead = Omit<components['schemas']['TestSuiteRead'], 'test_cases'> & {
  status: TestSuiteStatus
  test_cases: TestCaseRead[]
}
// Live-exploration NLM feature — not in api-types.gen.ts yet, added by hand.
// Mirrors `LiveTestCaseRequestStatusRead` (apps/api/src/api/main.py). Works
// with zero prior discovery data — no `NO_TEST_SUITE` gate on the create
// call; natural-language test-case creation always goes through live
// browser exploration (see `natural_language_flow.png`), never a match
// against a prior crawl.
export type LiveTestCaseRequestStatus =
  | 'exploring'
  | 'generating'
  | 'complete'
  | 'rejected'
  | 'failed'
// TEMP DEBUG — mirrors main.py's LiveTestCaseFieldRead/ComponentRead/PageRead,
// supporting the workflow's temporary exploration-only cutoff. Not permanent.
export type LiveTestCaseFieldRead = {
  name: string | null
  input_type: string
  required: boolean
  locator: string | null
}
export type LiveTestCaseComponentRead = {
  name: string
  type: string
  locator: string | null
}
export type LiveTestCasePageRead = {
  url: string
  heading: string | null
  fields: LiveTestCaseFieldRead[]
  components: LiveTestCaseComponentRead[]
}
export type LiveTestCaseGeneratedTestRead = {
  scenario_id: string
  name: string
  type: string
  code: string | null
}
export type LiveTestCaseRequestStatusRead = {
  request_id: string
  status: LiveTestCaseRequestStatus
  rejection_reason: string | null
  error_message: string | null
  journey_name: string | null
  pages: LiveTestCasePageRead[]
  generated_tests: LiveTestCaseGeneratedTestRead[]
}
// Not in api-types.gen.ts yet (backend schema is new, regenerate via
// `npm run generate:api-types` once the API is running) — added by hand.
export type InteractionLevel = 'passive' | 'normal' | 'aggressive'
export type RetentionPeriod = '1_day' | '1_week' | '1_month'
export type SettingsRead = {
  max_pages: number
  max_discovery_duration_minutes: number | null
  navigation_timeout_seconds: number
  interaction_level: InteractionLevel
  max_journeys: number | null
  max_scenarios_per_journey: number | null
  max_test_cases_per_application: number | null
  delete_project_after: RetentionPeriod
  max_heal_attempts: number
}
export type SettingsUpdate = Partial<SettingsRead>
// Not in api-types.gen.ts yet (backend schema is new, regenerate via
// `npm run generate:api-types` once the API is running) — added by hand.
export type ExecutionPolicyRead = {
  execution_enabled: boolean
  allowed_base_urls: string[]
  destructive_actions_permitted: boolean
  video_capture_enabled: boolean
  version: number
}
export type ExecutionPolicyUpdate = Partial<ExecutionPolicyRead>
export type TestResultStatus = 'pending' | 'passed' | 'failed' | 'timed_out' | 'errored' | 'blocked'
export type TestResultRead = {
  id: string
  scenario_name: string
  // Which Journey (suite) this result's Scenario belongs to — groups a
  // run's results "by suite" the same way TestSuiteTab groups assets.
  journey_name: string
  // Test Case Number feature — see ScenarioRead's own comment. null only if
  // the Scenario itself was hard-deleted since this result ran.
  test_case_number: number | null
  status: TestResultStatus
  duration_ms: number | null
  error_message: string | null
  stack_trace: string | null
  blocked_reason: string | null
  // Two independent budgets, never combined — see TestResultRead in
  // apps/api/src/api/main.py. auto_* is spent only by automatic healing,
  // capped at auto_heal_attempt_cap; manual_* is spent only by "Retry with
  // self-healing", capped at max_heal_attempts.
  auto_heal_attempt_count: number
  manual_heal_attempt_count: number
  healed_test_asset_id: string | null
  auto_heal_attempt_cap: number
  // The current DiscoverySettings.max_heal_attempts, read alongside every
  // result rather than a second admin-only GET /settings call — see
  // TestResultRead in apps/api/src/api/main.py.
  max_heal_attempts: number
}
export type TestRunStatus = 'pending' | 'running' | 'completed' | 'blocked'
export type TestRunRead = {
  id: string
  run_number: number
  name: string
  status: TestRunStatus
  trigger: string
  pass_rate: number | null
  health: HealthRead
  total_count: number
  passed_count: number
  failed_count: number
  timed_out_count: number
  errored_count: number
  blocked_count: number
  blocked_reason: string | null
  environment_snapshot: string
  target_base_url_snapshot: string
  created_at: string
  started_at: string | null
  completed_at: string | null
  results?: TestResultRead[] | null
}
export type TestRunCursorPageRead = {
  items: TestRunRead[]
  next_cursor: string | null
}
export type TestResultArtifactRead = {
  id: string
  artifact_type: 'screenshot' | 'trace' | 'video'
  content_type: string
  size_bytes: number
  url: string
}
// Application Workspace feature (Overview / Test Suite / Runs tabs) — not in
// api-types.gen.ts yet, added by hand per the same convention as the types
// above.
export type SuiteRowStatus = 'passed' | 'failed' | 'not_run'
export type TestAssetStatusRead = {
  id: string
  // Test Case Number feature — see ScenarioRead's own comment.
  test_case_number: number
  // Edit Test Data feature — this row's underlying Scenario, since
  // test_data lives there, not on the TestAsset itself. null only in the
  // same defensive missing-Scenario case every other field above falls
  // back for.
  scenario_id: string | null
  name: string
  journey_name: string
  type: string
  steps: string[]
  status: SuiteRowStatus
  last_run_at: string | null
  duration_ms: number | null
  error_message: string | null
  latest_test_result_id: string | null
  // NLM "Add Test Case" feature — see TestCaseRead's own comment.
  source: TestCaseSource
}
export type TestAssetStatusPageRead = {
  items: TestAssetStatusRead[]
  page: number
  page_size: number
  total: number
}
export type TestAssetCodeRead = { code: string }
// Edit Test Data (Test Suite page) — not in api-types.gen.ts yet, added by
// hand per the same convention as the types above.
export type RegenerateTestAssetStatusRead = {
  status: 'running' | 'complete' | 'failed'
  test_asset_id: string | null
  error_message: string | null
}
// Scenarios tab "Auto-generate" (test data) — not in api-types.gen.ts yet,
// added by hand per the same convention.
export type AutofillScenarioTestDataStatusRead = {
  status: 'running' | 'complete' | 'failed'
  // Full Scenario, not just its test_data — test_data_complete is computed
  // at read time, so the caller needs the freshly-converted Scenario for an
  // accurate readiness pill (same as updateScenarioTestData's response).
  scenario: ScenarioRead | null
  error_message: string | null
}
export type HealthTier = 'healthy' | 'needs_attention' | 'critical'
export type HealthRead = { tier: HealthTier; headline: string }
export type RunTrendPointRead = { run_id: string; run_number: number; pass_rate: number | null; created_at: string }
export type LatestRunSummaryRead = {
  id: string
  created_at: string
  passed_count: number
  failed_count: number
  blocked_count: number
  duration_ms: number | null
  trigger: string
}
export type OverviewRead = {
  health: HealthRead
  total_tests: number
  passed: number
  failed: number
  not_run: number
  pass_rate: number | null
  trend: RunTrendPointRead[]
  latest_run: LatestRunSummaryRead | null
  last_discovery_started_at: string | null
  journey_count: number
}
// Schedules feature — not in api-types.gen.ts yet, added by hand per the
// same convention as the types above.
export type ScheduleCadenceType = 'daily' | 'weekly' | 'monthly' | 'custom_cron'
export type ScheduleRead = {
  id: string
  name: string
  cadence_type: ScheduleCadenceType
  hour: number | null
  minute: number | null
  days_of_week: number[]
  day_of_month: number | null
  cron_expression: string | null
  time_zone: string
  enabled: boolean
  cadence_label: string
  next_run_at: string | null
  created_by_name: string | null
  created_at: string
}
export type ScheduleCreate = {
  name: string
  cadence_type: ScheduleCadenceType
  hour?: number | null
  minute?: number | null
  days_of_week?: number[]
  day_of_month?: number | null
  cron_expression?: string | null
}
export type ScheduleUpdate = Partial<ScheduleCreate>

const API_BASE = import.meta.env.VITE_API_BASE || 'http://localhost:8000'

class ApiError extends Error {
  status: number

  constructor(message: string, status: number) {
    super(message)
    this.status = status
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${API_BASE}${path}`, {
    credentials: 'include',
    headers: { 'Content-Type': 'application/json' },
    ...init,
  })
  if (!response.ok) {
    const body = await response.json().catch(() => null)
    // A 401 here always means the session cookie itself was rejected (bad
    // signature or the 1-hour idle window expired) — /auth/login's own 401
    // is a wrong-password rejection, not a session expiry, so it's excluded.
    if (response.status === 401 && path !== '/auth/login') {
      window.dispatchEvent(new CustomEvent('auth:expired'))
    }
    throw new ApiError(body?.detail ?? response.statusText, response.status)
  }
  if (response.status === 204) return undefined as T
  return response.json() as Promise<T>
}

export const api = {
  login: (payload: LoginRequest) =>
    request<UserRead>('/auth/login', { method: 'POST', body: JSON.stringify(payload) }),
  logout: () => request<{ status: string }>('/auth/logout', { method: 'POST' }),
  me: () => request<UserRead>('/auth/me'),
  sendInvite: (payload: InviteCreate) =>
    request<InviteRead>('/invites', { method: 'POST', body: JSON.stringify(payload) }),
  listInvites: () => request<InviteRead[]>('/invites'),
  revokeInvite: (inviteId: string) =>
    request<undefined>(`/invites/${inviteId}`, { method: 'DELETE' }),
  acceptInvite: (payload: AcceptInviteRequest) =>
    request<UserRead>('/invites/accept', { method: 'POST', body: JSON.stringify(payload) }),
  forgotPassword: (payload: ForgotPasswordRequest) =>
    request<{ status: string }>('/auth/forgot-password', { method: 'POST', body: JSON.stringify(payload) }),
  getResetPasswordTarget: (token: string) =>
    request<ResetPasswordTarget>(`/auth/reset-password?token=${encodeURIComponent(token)}`),
  resetPassword: (payload: ResetPasswordRequest) =>
    request<UserRead>('/auth/reset-password', { method: 'POST', body: JSON.stringify(payload) }),
  createApplication: (payload: ApplicationCreate) =>
    request<ApplicationRead>('/applications', { method: 'POST', body: JSON.stringify(payload) }),
  testConnection: (url: string) =>
    request<{ reachable: boolean; detail: string | null }>('/applications/test-connection', {
      method: 'POST',
      body: JSON.stringify({ url }),
    }),
  listApplications: () => request<ApplicationRead[]>('/applications'),
  getHome: () => request<HomeApplicationRead[]>('/home'),
  getOverviewStats: () => request<OverviewStatsRead>('/overview-stats'),
  getApplication: (applicationId: string) =>
    request<ApplicationRead>(`/applications/${applicationId}`),
  renameApplication: (applicationId: string, name: string) =>
    request<ApplicationRead>(`/applications/${applicationId}`, {
      method: 'PATCH',
      body: JSON.stringify({ name }),
    }),
  updateApplicationCredentials: (
    applicationId: string,
    username: string,
    password: string,
    mfa?: { enabled: boolean; totpSeed: string },
  ) =>
    request<ApplicationRead>(`/applications/${applicationId}/credentials`, {
      method: 'PATCH',
      body: JSON.stringify({
        username,
        password,
        mfa_enabled: mfa?.enabled ?? false,
        totp_seed: mfa?.totpSeed,
      }),
    }),
  deleteApplication: (applicationId: string) =>
    request<undefined>(`/applications/${applicationId}`, { method: 'DELETE' }),
  listTeam: () =>
    request<{ name: string; email: string; role: 'admin' | 'member'; created_at: string; last_active_at: string | null }[]>(
      '/team',
    ),
  removeTeamMember: (email: string) =>
    request<undefined>(`/team/${encodeURIComponent(email)}`, { method: 'DELETE' }),
  listCredentials: () =>
    request<
      { application_id: string; application_name: string; environment: string; username: string; has_password: boolean }[]
    >('/credentials'),
  revealCredential: (applicationId: string) =>
    request<{ password: string }>(`/credentials/${applicationId}/reveal`, { method: 'POST' }),
  verifyCredential: (applicationId: string) =>
    request<{ reachable: boolean; detail: string | null }>(`/credentials/${applicationId}/verify`, { method: 'POST' }),
  pauseDiscovery: (applicationId: string) =>
    request<ApplicationRead>(`/applications/${applicationId}/pause-discovery`, { method: 'POST' }),
  resumeDiscovery: (applicationId: string) =>
    request<ApplicationRead>(`/applications/${applicationId}/resume-discovery`, { method: 'POST' }),
  listJourneys: (applicationId: string) =>
    request<JourneyRead[]>(`/applications/${applicationId}/journeys`),
  listJourneySteps: (journeyId: string) =>
    request<JourneyStepRead[]>(`/journeys/${journeyId}/steps`),
  renameJourney: (journeyId: string, name: string) =>
    request<JourneyRead>(`/journeys/${journeyId}`, {
      method: 'PATCH',
      body: JSON.stringify({ name }),
    }),
  deleteJourney: (journeyId: string) =>
    request<undefined>(`/journeys/${journeyId}`, { method: 'DELETE' }),
  generateScenarios: (applicationId: string) =>
    request<{ journeys_triggered: number }>(`/applications/${applicationId}/generate-scenarios`, {
      method: 'POST',
    }),
  listScenarios: (applicationId: string) =>
    request<ScenarioRead[]>(`/applications/${applicationId}/scenarios`),
  renameScenario: (scenarioId: string, name: string) =>
    request<ScenarioRead>(`/scenarios/${scenarioId}`, {
      method: 'PATCH',
      body: JSON.stringify({ name }),
    }),
  deleteScenario: (scenarioId: string) =>
    request<undefined>(`/scenarios/${scenarioId}`, { method: 'DELETE' }),
  updateScenarioTestData: (scenarioId: string, name: string, value: string) =>
    request<ScenarioRead>(`/scenarios/${scenarioId}/test-data`, {
      method: 'PATCH',
      body: JSON.stringify({ name, value }),
    }),
  // Edit Test Data (Test Suite page) — regenerates the Scenario's current
  // TestAsset as a targeted AI edit, only after every changed field above
  // has already saved successfully.
  regenerateTestAsset: (scenarioId: string) =>
    request<{ started: boolean }>(`/scenarios/${scenarioId}/test-data/regenerate`, {
      method: 'POST',
    }),
  getRegenerateTestAssetStatus: (scenarioId: string) =>
    request<RegenerateTestAssetStatusRead>(`/scenarios/${scenarioId}/test-data/regenerate`),
  // Auto-generate test data — deterministic default fill, no AI, distinct
  // from regenerateTestAsset above (that's an AI code edit after a manual
  // change; this only ever fills still-blank fields).
  autofillScenarioTestData: (scenarioId: string) =>
    request<{ started: boolean }>(`/scenarios/${scenarioId}/test-data/auto-fill`, {
      method: 'POST',
    }),
  getAutofillScenarioTestDataStatus: (scenarioId: string) =>
    request<AutofillScenarioTestDataStatusRead>(`/scenarios/${scenarioId}/test-data/auto-fill`),
  generateSuite: (applicationId: string) =>
    request<{ suites_triggered: number }>(`/applications/${applicationId}/generate-suite`, {
      method: 'POST',
    }),
  listTestSuites: (applicationId: string) =>
    request<TestSuiteRead[]>(`/applications/${applicationId}/test-suites`),
  terminateTestSuite: (applicationId: string, suiteId: string) =>
    request<TestSuiteRead>(`/applications/${applicationId}/test-suites/${suiteId}/terminate`, {
      method: 'POST',
    }),
  createLiveTestCase: (applicationId: string, prompt: string) =>
    request<{ request_id: string }>(`/applications/${applicationId}/live-test-cases`, {
      method: 'POST',
      body: JSON.stringify({ prompt }),
    }),
  getLiveTestCaseRequest: (applicationId: string, requestId: string) =>
    request<LiveTestCaseRequestStatusRead>(
      `/applications/${applicationId}/live-test-cases/requests/${requestId}`,
    ),
  getGenerationStatus: (applicationId: string) =>
    request<{ available: boolean }>(`/applications/${applicationId}/generation-status`),
  getDiscoveryStatus: (applicationId: string) =>
    request<{ available: boolean; retry_count: number }>(
      `/applications/${applicationId}/discovery-status`,
    ),
  getExecutionStatus: (applicationId: string) =>
    request<{ available: boolean }>(`/applications/${applicationId}/execution-status`),
  listSchedules: (applicationId: string) =>
    request<ScheduleRead[]>(`/applications/${applicationId}/schedules`),
  createSchedule: (applicationId: string, payload: ScheduleCreate) =>
    request<ScheduleRead>(`/applications/${applicationId}/schedules`, {
      method: 'POST',
      body: JSON.stringify(payload),
    }),
  updateSchedule: (scheduleId: string, payload: ScheduleUpdate) =>
    request<ScheduleRead>(`/schedules/${scheduleId}`, {
      method: 'PATCH',
      body: JSON.stringify(payload),
    }),
  deleteSchedule: (scheduleId: string) =>
    request<undefined>(`/schedules/${scheduleId}`, { method: 'DELETE' }),
  enableSchedule: (scheduleId: string) =>
    request<ScheduleRead>(`/schedules/${scheduleId}/enable`, { method: 'POST' }),
  disableSchedule: (scheduleId: string) =>
    request<ScheduleRead>(`/schedules/${scheduleId}/disable`, { method: 'POST' }),
  runScheduleNow: (scheduleId: string) =>
    request<{ started: boolean }>(`/schedules/${scheduleId}/run-now`, { method: 'POST' }),
  getSettings: () => request<SettingsRead>('/settings'),
  updateSettings: (payload: SettingsUpdate) =>
    request<SettingsRead>('/settings', { method: 'PATCH', body: JSON.stringify(payload) }),
  getExecutionPolicy: (applicationId: string) =>
    request<ExecutionPolicyRead>(`/applications/${applicationId}/execution-policy`),
  updateExecutionPolicy: (applicationId: string, payload: ExecutionPolicyUpdate) =>
    request<ExecutionPolicyRead>(`/applications/${applicationId}/execution-policy`, {
      method: 'PUT',
      body: JSON.stringify(payload),
    }),
  triggerTestRun: (
    applicationId: string,
    payload?: { suite_name: string; test_case_ids: string[] },
  ) =>
    request<{ started: boolean }>(`/applications/${applicationId}/test-runs`, {
      method: 'POST',
      ...(payload ? { body: JSON.stringify(payload) } : {}),
    }),
  listTestRuns: (applicationId: string, cursor: string | null = null, limit = 10, q = '') =>
    request<TestRunCursorPageRead>(
      `/applications/${applicationId}/test-runs?limit=${limit}${cursor ? `&cursor=${encodeURIComponent(cursor)}` : ''}${
        q ? `&q=${encodeURIComponent(q)}` : ''
      }`,
    ),
  getTestRun: (applicationId: string, testRunId: string) =>
    request<TestRunRead>(`/applications/${applicationId}/test-runs/${testRunId}`),
  listTestResultArtifacts: (testResultId: string) =>
    request<TestResultArtifactRead[]>(`/test-results/${testResultId}/artifacts`),
  healTestResult: (testResultId: string) =>
    request<{ started: boolean }>(`/test-results/${testResultId}/heal`, { method: 'POST' }),
  getTestSuiteStatus: (applicationId: string, page = 1, pageSize = 10, q = '') =>
    request<TestAssetStatusPageRead>(
      `/applications/${applicationId}/test-suite-status?page=${page}&page_size=${pageSize}${
        q ? `&q=${encodeURIComponent(q)}` : ''
      }`,
    ),
  getTestAssetCode: (testAssetId: string) =>
    request<TestAssetCodeRead>(`/test-assets/${testAssetId}/code`),
  getOverview: (applicationId: string) =>
    request<OverviewRead>(`/applications/${applicationId}/overview`),
  // Not built on request<T>() — that helper always calls response.json(),
  // which throws on a binary zip body (Story 4.3).
  downloadTestSuiteProject: async (applicationId: string) => {
    const response = await fetch(
      `${API_BASE}/applications/${applicationId}/test-suites/download`,
      { credentials: 'include' },
    )
    if (!response.ok) {
      const body = await response.json().catch(() => null)
      throw new ApiError(body?.detail ?? response.statusText, response.status)
    }
    const blob = await response.blob()
    const disposition = response.headers.get('Content-Disposition') ?? ''
    const match = /filename="([^"]+)"/.exec(disposition)
    const filename = match?.[1] ?? 'tests.zip'
    const url = URL.createObjectURL(blob)
    try {
      const link = document.createElement('a')
      link.href = url
      link.download = filename
      document.body.appendChild(link)
      link.click()
      document.body.removeChild(link)
    } finally {
      URL.revokeObjectURL(url)
    }
  },
}

export { ApiError }
