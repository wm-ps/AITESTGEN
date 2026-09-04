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
}
export type JourneyRead = components['schemas']['JourneyRead']
export type JourneyStepRead = components['schemas']['JourneyStepRead']
export type ScenarioRead = components['schemas']['ScenarioRead']
// `description` isn't in api-types.gen.ts yet (regenerate via `npm run
// generate:api-types` once the API is running) — added by hand.
// NLM "Add Test Case" feature — 'discovery' (normal Discovery -> Journey ->
// Scenario pipeline) or 'nlm' (created ad hoc from a plain-English request).
// Mirrors `Scenario.source`/`TestCaseRead.source` (apps/api/src/api/main.py).
export type TestCaseSource = 'discovery' | 'nlm'
export type TestCaseRead = components['schemas']['TestCaseRead'] & {
  description: string
  source: TestCaseSource
}
// `status` isn't in api-types.gen.ts yet (regenerate via `npm run
// generate:api-types` once the API is running) — added by hand.
export type TestSuiteStatus = 'generating' | 'complete' | 'incomplete' | 'terminated'
export type TestSuiteRead = Omit<components['schemas']['TestSuiteRead'], 'test_cases'> & {
  status: TestSuiteStatus
  test_cases: TestCaseRead[]
}
// NLM "Add Test Case" feature — not in api-types.gen.ts yet (backend schema
// is new, regenerate via `npm run generate:api-types` once the API is
// running) — added by hand. Mirrors `TestCaseRequestStatusRead`
// (apps/api/src/api/main.py).
export type TestCaseRequestStatus = 'analyzing' | 'generating' | 'complete' | 'failed' | 'rejected'
// One Scenario's own outcome — a single prompt can decompose into several
// (Multiple Test Cases), each independently PASS/FAIL.
export type TestCaseGenerationResultRead = {
  status: 'complete' | 'failed'
  journey_name: string | null
  scenario_name: string | null
  test_result_status: string | null
  error_message: string | null
  // True when this Scenario already existed and was matched/reused as-is —
  // never (re)generated or re-run.
  already_existed: boolean
  // True only for a genuinely new Journey this request created.
  is_new_journey: boolean
  // True for a brand-new Scenario (existing Journey or one just created for
  // it); false for a genuine reuse_scenario match. Meaningless once
  // already_existed or is_new_journey is true.
  is_new_scenario: boolean
  // Set only when status is 'failed' — which step actually blocked creation.
  stage: string | null
}
export type TestCaseRequestStatusRead = {
  request_id: string
  status: TestCaseRequestStatus
  functionality_summary: string
  rejection_reason: string | null
  error_message: string | null
  scenario_count: number
  results: TestCaseGenerationResultRead[]
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
  name: string
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
export type HealthTier = 'healthy' | 'needs_attention' | 'critical'
export type HealthRead = { tier: HealthTier; headline: string }
export type RunTrendPointRead = { run_id: string; pass_rate: number | null; created_at: string }
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
  time_zone: string
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
  listApplications: () => request<ApplicationRead[]>('/applications'),
  getHome: () => request<HomeApplicationRead[]>('/home'),
  getApplication: (applicationId: string) =>
    request<ApplicationRead>(`/applications/${applicationId}`),
  renameApplication: (applicationId: string, name: string) =>
    request<ApplicationRead>(`/applications/${applicationId}`, {
      method: 'PATCH',
      body: JSON.stringify({ name }),
    }),
  updateApplicationCredentials: (applicationId: string, username: string, password: string) =>
    request<ApplicationRead>(`/applications/${applicationId}/credentials`, {
      method: 'PATCH',
      body: JSON.stringify({ username, password }),
    }),
  deleteApplication: (applicationId: string) =>
    request<undefined>(`/applications/${applicationId}`, { method: 'DELETE' }),
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
  createTestCase: (applicationId: string, prompt: string) =>
    request<{ request_id: string }>(`/applications/${applicationId}/test-cases`, {
      method: 'POST',
      body: JSON.stringify({ prompt }),
    }),
  getTestCaseRequest: (applicationId: string, requestId: string) =>
    request<TestCaseRequestStatusRead>(
      `/applications/${applicationId}/test-cases/requests/${requestId}`,
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
  triggerTestRun: (applicationId: string) =>
    request<{ started: boolean }>(`/applications/${applicationId}/test-runs`, { method: 'POST' }),
  listTestRuns: (applicationId: string, cursor: string | null = null, limit = 10) =>
    request<TestRunCursorPageRead>(
      `/applications/${applicationId}/test-runs?limit=${limit}${cursor ? `&cursor=${encodeURIComponent(cursor)}` : ''}`,
    ),
  getTestRun: (applicationId: string, testRunId: string) =>
    request<TestRunRead>(`/applications/${applicationId}/test-runs/${testRunId}`),
  listTestResultArtifacts: (testResultId: string) =>
    request<TestResultArtifactRead[]>(`/test-results/${testResultId}/artifacts`),
  healTestResult: (testResultId: string) =>
    request<{ started: boolean }>(`/test-results/${testResultId}/heal`, { method: 'POST' }),
  getTestSuiteStatus: (applicationId: string, page = 1, pageSize = 10) =>
    request<TestAssetStatusPageRead>(
      `/applications/${applicationId}/test-suite-status?page=${page}&page_size=${pageSize}`,
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
