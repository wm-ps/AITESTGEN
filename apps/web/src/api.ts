import type { components } from './api-types.gen'

export type UserRead = components['schemas']['UserRead']
export type LoginRequest = components['schemas']['LoginRequest']
export type ApplicationCreate = components['schemas']['ApplicationCreate']
export type ApplicationRead = components['schemas']['ApplicationRead']
export type JourneyRead = components['schemas']['JourneyRead']
export type JourneyStepRead = components['schemas']['JourneyStepRead']
export type ScenarioRead = components['schemas']['ScenarioRead']
export type TestCaseRead = components['schemas']['TestCaseRead']
export type TestSuiteRead = components['schemas']['TestSuiteRead']

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
  createApplication: (payload: ApplicationCreate) =>
    request<ApplicationRead>('/applications', { method: 'POST', body: JSON.stringify(payload) }),
  getApplication: (applicationId: string) =>
    request<ApplicationRead>(`/applications/${applicationId}`),
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
