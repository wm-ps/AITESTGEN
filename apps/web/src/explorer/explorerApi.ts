import { API_BASE, request } from '../api'

// Vantage Explorer — standalone module (docs/vantage-explorer/PLAN.md).

export type ExplorerStatus =
  | 'queued'
  | 'signing_in'
  | 'understanding'
  | 'summarizing'
  | 'awaiting_confirmation'
  | 'confirmed'
  | 'planning'
  | 'exploring'
  | 'explored'
  | 'hunting'
  | 'testing'
  | 'tested'
  | 'failed'
  | 'stopped'
  | 'paused'
  | 'expired'

export const WORKING_STATUSES: ExplorerStatus[] = ['queued', 'signing_in', 'understanding', 'summarizing', 'confirmed', 'planning', 'exploring', 'hunting', 'testing']

export type AppBrief = {
  app_name?: string
  one_liner?: string
  domain?: string
  who_uses_it?: { role: string; goal: string }[]
  business_things?: { name: string; description: string; statuses?: string[] }[]
  key_tasks?: { name: string; why_it_matters?: string; steps?: string[] }[]
  rules_we_expect?: { rule: string; source: string; confidence: string }[]
  hidden_parts_suspected?: { where: string; what: string; why: string }[]
  questions_for_you?: { question: string; options: string[]; answer?: string }[]
  // Set by you at review: what to focus on, and screens to leave out.
  focus?: string
  skip_screens?: string[]
}

export type ExplorerRun = {
  id: string
  application_id: string
  status: ExplorerStatus
  headline: string
  health_score: number | null
  requirements_first: boolean
  brief: AppBrief | null
  brief_confirmed_at: string | null
  notes: string | null
  error: string | null
  created_at: string
  updated_at: string
  counts: {
    screens: number
    hidden_hints: number
    health_issues: number
    hidden_screens: number
    possible_bugs: number
    missions_total: number
    missions_done: number
    missions_running: number
    tests_total: number
    tests_proven: number
    tests_known_bugs: number
    tests_building: number
    questions_open: number
  }
}

export type ExplorerEventKind = 'thought' | 'action' | 'screen' | 'health' | 'phase' | 'summary' | 'error' | 'question'

export type ExplorerEvent = {
  id: number
  kind: ExplorerEventKind
  title: string
  detail: string | null
  shot_id: string | null
  mission_id: string | null
  created_at: string
}

export type ExplorerScreen = {
  id: string
  name: string
  entity: string | null
  view_kind: string
  mode: string | null
  purpose: string | null
  url: string
  visits: number
  fields: { label: string; type?: string; required?: boolean; notes?: string }[]
  actions: { label: string; kind?: string; risky?: boolean }[]
  hidden_hints: string[]
  reached_by: string | null
  shot_id: string | null
  condition: string | null
}

export type MissionStatus = 'queued' | 'running' | 'waiting' | 'done' | 'blocked' | 'failed' | 'skipped'

export type ExplorerMission = {
  id: string
  title: string
  goal: string
  kind: 'task' | 'branch' | 'area' | 'rule' | 'custom' | string
  why: string | null
  priority: number
  instructions: string | null
  condition: string | null
  expected: string | null
  status: MissionStatus
  outcome: string | null
  matches_expected: boolean | null
  steps: number
  new_screens: number
  added_by: 'explorer' | 'user' | string
  started_at: string | null
  finished_at: string | null
  recording: { started_at: string; duration_seconds: number } | null
}

export type AppMap = {
  screens: ExplorerScreen[]
  edges: { from_id: string; to_id: string; action: string }[]
}

export type TestKind = 'navigation' | 'validation' | 'error_state' | 'data_load' | 'form_submission' | 'journey'

export type ExplorerTestCase = {
  id: string
  kind: TestKind
  title: string
  purpose: string
  technique: string | null
  business_thing: string | null
  start_screen: string | null
  steps: string[]
  expected: string
  trust: 'confirmed' | 'standard' | 'seen' | string
  observed: string | null
  check: { kind: string; value: string } | null
  status: 'planned' | 'building' | 'proven' | 'known_bug' | 'dropped'
  drop_reason: string | null
  proof_runs: number
  proof_passes: number
  catches_breakage: boolean | null
  evidence_shot_id: string | null
  code: string | null
  has_proof_video: boolean
  coverage?: string | null
  linked_to?: string | null
}

export type ExplorerQuestion = {
  id: string
  kind: 'data' | 'risk' | 'rule' | 'clarify' | string
  question: string
  why: string | null
  options: string[]
  shot_id: string | null
  status: 'open' | 'answered' | 'dismissed'
  answer: string | null
  answered_at: string | null
  created_at: string
  mission_title: string | null
}

export type ExplorerKnowledge = {
  id: string
  kind: 'answer' | 'doc' | 'fact' | string
  text: string
  source: string | null
  created_at: string
}

export type ExplorerRole = { id: string; name: string; created_at: string }

export type ExplorerReport = {
  run: ExplorerRun
  application_name: string
  hidden_screens: ExplorerScreen[]
  possible_bugs: ExplorerHealthIssue[]
  known_bug_tests: ExplorerTestCase[]
  tests_by_kind: Record<string, { proven: number; known_bug: number; dropped: number }>
  missions: ExplorerMission[]
  access: { role: string; screen_id: string; allowed: boolean; note: string | null }[]
  access_screens: ExplorerScreen[]
  insights: {
    coverage?: { functions: number; ran: number; percent: number; never_ran: string[] }
    unlinked?: string[]
    roles?: { role: string; signed_in: boolean; allowed?: number; blocked?: number }[]
  }
  has_reel: boolean
}

export type ExplorerHealthIssue = {
  id: string
  kind: string
  severity: 'high' | 'medium' | 'low'
  title: string
  detail: string | null
  url: string
  occurrences: number
  shot_id: string | null
}

export const shotUrl = (shotId: string) => `${API_BASE}/explorer/shots/${shotId}`
export const recordingUrl = (missionId: string) => `${API_BASE}/explorer/missions/${missionId}/recording`
export const proofUrl = (testId: string) => `${API_BASE}/explorer/tests/${testId}/proof`
export const reelUrl = (runId: string) => `${API_BASE}/explorer/runs/${runId}/reel`
export const reportDownloadUrl = (runId: string) => `${API_BASE}/explorer/runs/${runId}/report/download`
export const testsDownloadUrl = (runId: string) => `${API_BASE}/explorer/runs/${runId}/tests/download`

export const explorerApi = {
  latestRun: (applicationId: string) =>
    request<ExplorerRun | null>(`/explorer/applications/${applicationId}/runs/latest`),
  startRun: (applicationId: string) =>
    request<ExplorerRun>(`/explorer/applications/${applicationId}/runs`, {
      method: 'POST',
      body: JSON.stringify({ notes: '' }),
    }),
  getRun: (runId: string) => request<ExplorerRun>(`/explorer/runs/${runId}`),
  events: (runId: string, after: number) =>
    request<ExplorerEvent[]>(`/explorer/runs/${runId}/events?after=${after}`),
  screens: (runId: string) => request<ExplorerScreen[]>(`/explorer/runs/${runId}/screens`),
  health: (runId: string) => request<ExplorerHealthIssue[]>(`/explorer/runs/${runId}/health`),
  falseAlarm: (issueId: string) => request<undefined>(`/explorer/health/${issueId}/false-alarm`, { method: 'POST' }),
  saveBrief: (runId: string, brief: AppBrief) =>
    request<ExplorerRun>(`/explorer/runs/${runId}/brief`, { method: 'PUT', body: JSON.stringify(brief) }),
  confirm: (runId: string) => request<ExplorerRun>(`/explorer/runs/${runId}/confirm`, { method: 'POST' }),
  stop: (runId: string) => request<ExplorerRun>(`/explorer/runs/${runId}/stop`, { method: 'POST' }),
  pause: (runId: string) => request<ExplorerRun>(`/explorer/runs/${runId}/pause`, { method: 'POST' }),
  resume: (runId: string) => request<ExplorerRun>(`/explorer/runs/${runId}/resume`, { method: 'POST' }),
  missions: (runId: string) => request<ExplorerMission[]>(`/explorer/runs/${runId}/missions`),
  addMission: (runId: string, goal: string) =>
    request<ExplorerMission>(`/explorer/runs/${runId}/missions`, { method: 'POST', body: JSON.stringify({ goal }) }),
  skipMission: (missionId: string) =>
    request<ExplorerMission>(`/explorer/missions/${missionId}/skip`, { method: 'POST' }),
  map: (runId: string) => request<AppMap>(`/explorer/runs/${runId}/map`),
  tests: (runId: string) => request<ExplorerTestCase[]>(`/explorer/runs/${runId}/tests`),
  verdict: (testId: string, verdict: 'not_a_bug' | 'ignore') =>
    request<ExplorerRun>(`/explorer/tests/${testId}/verdict`, { method: 'POST', body: JSON.stringify({ verdict }) }),
  questions: (runId: string) => request<ExplorerQuestion[]>(`/explorer/runs/${runId}/questions`),
  answer: (questionId: string, answer: string) =>
    request<ExplorerQuestion>(`/explorer/questions/${questionId}/answer`, { method: 'POST', body: JSON.stringify({ answer }) }),
  dismiss: (questionId: string) => request<ExplorerQuestion>(`/explorer/questions/${questionId}/dismiss`, { method: 'POST' }),
  knowledge: (applicationId: string) => request<ExplorerKnowledge[]>(`/explorer/applications/${applicationId}/knowledge`),
  addFact: (applicationId: string, text: string) =>
    request<ExplorerKnowledge>(`/explorer/applications/${applicationId}/knowledge`, { method: 'POST', body: JSON.stringify({ text }) }),
  deleteKnowledge: (knowledgeId: string) => request<undefined>(`/explorer/knowledge/${knowledgeId}`, { method: 'DELETE' }),
  uploadDocument: async (applicationId: string, file: File) => {
    // Multipart, so not the JSON request() helper.
    const form = new FormData()
    form.append('file', file)
    const response = await fetch(`${API_BASE}/explorer/applications/${applicationId}/knowledge/documents`, {
      method: 'POST',
      body: form,
      credentials: 'include',
    })
    if (!response.ok) {
      const body = await response.json().catch(() => null)
      throw new Error(body?.detail ?? 'Upload failed')
    }
    return (await response.json()) as ExplorerKnowledge[]
  },
  report: (runId: string) => request<ExplorerReport>(`/explorer/runs/${runId}/report`),
  roles: (applicationId: string) => request<ExplorerRole[]>(`/explorer/applications/${applicationId}/roles`),
  addRole: (applicationId: string, name: string, username: string, password: string) =>
    request<ExplorerRole>(`/explorer/applications/${applicationId}/roles`, { method: 'POST', body: JSON.stringify({ name, username, password }) }),
  deleteRole: (roleId: string) => request<undefined>(`/explorer/roles/${roleId}`, { method: 'DELETE' }),
  regenerateTests: (runId: string) =>
    request<ExplorerRun>(`/explorer/runs/${runId}/tests/regenerate`, { method: 'POST' }),
}
