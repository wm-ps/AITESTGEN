import { createRoot } from 'react-dom/client'
import './index.css'
import { GenerateSuite } from './components/GenerateSuite'
import { TestSuiteResults } from './components/TestSuiteResults'

const JOURNEYS = [
  { id: 'journey-1', name: 'Customer Login & MFA', description: null, step_count: 5 },
  { id: 'journey-2', name: 'Internal Funds Transfer', description: null, step_count: 4 },
]

const SCENARIOS = [
  { id: 's1', journey_id: 'journey-1', journey_name: 'Customer Login & MFA', type: 'happy', name: 'Successful login with valid credentials and MFA code', steps: [], expected_result: '', test_data: [], test_data_complete: true },
  { id: 's2', journey_id: 'journey-1', journey_name: 'Customer Login & MFA', type: 'negative', name: 'Login blocked after 3 invalid password attempts', steps: [], expected_result: '', test_data: [], test_data_complete: true },
  { id: 's3', journey_id: 'journey-1', journey_name: 'Customer Login & MFA', type: 'edge', name: 'MFA code expires after 5 minutes', steps: [], expected_result: '', test_data: [], test_data_complete: true },
  { id: 's4', journey_id: 'journey-2', journey_name: 'Internal Funds Transfer', type: 'happy', name: 'Transfer succeeds between own accounts', steps: [], expected_result: '', test_data: [], test_data_complete: true },
]

const SUITES = [
  {
    id: 'suite-1',
    name: 'Customer Login & MFA Suite',
    journey_name: 'Customer Login & MFA',
    test_cases: [
      { id: 'c1', name: 'Successful login with valid credentials and MFA code', type: 'happy', code: 'def test_login():\n    pass\n' },
      { id: 'c2', name: 'Login blocked after 3 invalid password attempts', type: 'negative', code: 'def test_blocked():\n    pass\n' },
      { id: 'c3', name: 'MFA code expires after 5 minutes', type: 'edge', code: 'def test_expires():\n    pass\n' },
    ],
  },
  {
    id: 'suite-2',
    name: 'Internal Funds Transfer Suite',
    journey_name: 'Internal Funds Transfer',
    test_cases: [
      { id: 'c4', name: 'Transfer succeeds between own accounts', type: 'happy', code: 'def test_transfer():\n    pass\n' },
    ],
  },
]

const originalFetch = window.fetch.bind(window)
window.fetch = (async (input: RequestInfo | URL, init?: RequestInit) => {
  const url = typeof input === 'string' ? input : input.toString()

  if (url.includes('/generating-app/')) {
    if (url.includes('/scenarios')) return jsonResponse(SCENARIOS)
    if (url.includes('/test-suites')) return jsonResponse([SUITES[0]].map((s) => ({ ...s, test_cases: s.test_cases.slice(0, 1) })))
    return jsonResponse([])
  }
  if (url.includes('/results-app/')) {
    if (url.includes('/scenarios')) return jsonResponse(SCENARIOS)
    if (url.includes('/test-suites')) return jsonResponse(SUITES)
    return jsonResponse([])
  }
  if (url.includes('/journeys')) return jsonResponse(JOURNEYS)
  if (url.includes('/scenarios')) return jsonResponse(SCENARIOS)
  return jsonResponse([])
}) as typeof window.fetch

function jsonResponse(data: unknown) {
  return Promise.resolve(new Response(JSON.stringify(data), { status: 200 }))
}
void originalFetch

createRoot(document.getElementById('root-generate')!).render(
  <GenerateSuite applicationId="generate-app" onGenerated={() => {}} />,
)
createRoot(document.getElementById('root-generating')!).render(
  <TestSuiteResults applicationId="generating-app" onGoToDashboard={() => {}} />,
)
createRoot(document.getElementById('root-results')!).render(
  <TestSuiteResults applicationId="results-app" onGoToDashboard={() => {}} />,
)
