import { useEffect, useState } from 'react'
import type { components } from './api-types.gen'

// Proof-of-wiring only (Story 1.1, AC3): this type is generated from apps/api's
// OpenAPI spec (AD-6) — no hand-written duplicate of this shape exists here.
type ScaffoldProbe = components['schemas']['ScaffoldProbe']

const API_BASE_URL = 'http://localhost:8000'

export function ScaffoldProbeView() {
  const [probe, setProbe] = useState<ScaffoldProbe | null>(null)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    fetch(`${API_BASE_URL}/scaffold-probe`, { method: 'POST' })
      .then((res) => {
        if (!res.ok) throw new Error(`request failed: ${res.status}`)
        return res.json() as Promise<ScaffoldProbe>
      })
      .then(setProbe)
      .catch((err: Error) => setError(err.message))
  }, [])

  if (error) return <p role="alert">Scaffold probe failed: {error}</p>
  if (!probe) return <p>Loading scaffold probe…</p>

  return (
    <div>
      <h1>Scaffold probe</h1>
      <p>id: {probe.id}</p>
      <p>note: {probe.note}</p>
      <p>created_at: {probe.created_at}</p>
    </div>
  )
}
