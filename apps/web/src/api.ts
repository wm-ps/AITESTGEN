import type { components } from './api-types.gen'

// `role` isn't in api-types.gen.ts yet (that file is generated from a
// running API's OpenAPI schema, regenerate via `npm run generate:api-types`)
// — added by hand for now rather than blocking this on a live server.
export type UserRead = components['schemas']['UserRead'] & { role: 'admin' | 'member' }
export type LoginRequest = components['schemas']['LoginRequest']
export type InviteCreate = { email: string; role: 'admin' | 'member' }
export type InviteRead = { id: string; email: string; role: 'admin' | 'member'; expires_at: string }
export type AcceptInviteRequest = { token: string; name: string; password: string }
export type ApplicationCreate = components['schemas']['ApplicationCreate']
export type ApplicationRead = components['schemas']['ApplicationRead']
export type JourneyRead = components['schemas']['JourneyRead']
export type JourneyStepRead = components['schemas']['JourneyStepRead']
export type ScenarioRead = components['schemas']['ScenarioRead']
export type TestCaseRead = components['schemas']['TestCaseRead']
export type TestSuiteRead = components['schemas']['TestSuiteRead']
// Not in api-types.gen.ts yet (backend schema is new, regenerate via
// `npm run generate:api-types` once the API is running) — added by hand.
export type InteractionLevel = 'passive' | 'normal' | 'aggressive'
export type SettingsRead = {
  max_pages: number
  max_discovery_duration_minutes: number
  navigation_timeout_seconds: number
  interaction_level: InteractionLevel
}
export type SettingsUpdate = Partial<SettingsRead>

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
  createApplication: (payload: ApplicationCreate) =>
    request<ApplicationRead>('/applications', { method: 'POST', body: JSON.stringify(payload) }),
  listApplications: () => request<ApplicationRead[]>('/applications'),
  getApplication: (applicationId: string) =>
    request<ApplicationRead>(`/applications/${applicationId}`),
  renameApplication: (applicationId: string, name: string) =>
    request<ApplicationRead>(`/applications/${applicationId}`, {
      method: 'PATCH',
      body: JSON.stringify({ name }),
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
  getSettings: () => request<SettingsRead>('/settings'),
  updateSettings: (payload: SettingsUpdate) =>
    request<SettingsRead>('/settings', { method: 'PATCH', body: JSON.stringify(payload) }),
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
