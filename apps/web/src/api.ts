import type { components } from './api-types.gen'

export type UserRead = components['schemas']['UserRead']
export type LoginRequest = components['schemas']['LoginRequest']
export type ApplicationCreate = components['schemas']['ApplicationCreate']
export type ApplicationRead = components['schemas']['ApplicationRead']
export type CaptureRead = components['schemas']['CaptureRead']
export type JourneyRead = components['schemas']['JourneyRead']
export type JourneyStepRead = components['schemas']['JourneyStepRead']

const API_BASE = import.meta.env.VITE_API_BASE ?? 'http://localhost:8000'

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
  listCaptures: (discoveryRunId: string) =>
    request<CaptureRead[]>(`/discovery-runs/${discoveryRunId}/captures`),
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
}

export { ApiError }
