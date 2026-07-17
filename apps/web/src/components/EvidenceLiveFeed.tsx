import { useEffect, useState } from 'react'
import { api, type EvidenceRead } from '../api'

const POLL_INTERVAL_MS = 1500

export function EvidenceLiveFeed({
  discoveryRunId,
  active,
}: {
  discoveryRunId: string
  active: boolean
}) {
  const [evidence, setEvidence] = useState<EvidenceRead[]>([])

  useEffect(() => {
    let cancelled = false

    async function poll() {
      try {
        const rows = await api.listEvidence(discoveryRunId)
        if (!cancelled) setEvidence(rows)
      } catch {
        // best-effort live feed — a transient poll failure just skips this tick
      }
    }

    poll()
    if (!active) return
    const interval = setInterval(poll, POLL_INTERVAL_MS)
    return () => {
      cancelled = true
      clearInterval(interval)
    }
  }, [discoveryRunId, active])

  if (evidence.length === 0) return null

  return (
    <div className="card-panel" style={{ padding: 'var(--space-5)', marginTop: 'var(--space-5)' }}>
      <div className="label" style={{ marginBottom: 'var(--space-3)' }}>
        Live discovery feed
      </div>
      <ul
        style={{
          listStyle: 'none',
          margin: 0,
          padding: 0,
          display: 'flex',
          flexDirection: 'column',
          gap: 'var(--space-2)',
          maxHeight: 260,
          overflowY: 'auto',
        }}
      >
        {evidence.map((item, index) => (
          <li
            key={`${item.captured_at}-${index}`}
            style={{ fontFamily: 'var(--font-mono)', fontSize: 12.5, color: 'var(--ink-muted)' }}
          >
            [{item.type}] {JSON.stringify(item.details)}
          </li>
        ))}
      </ul>
    </div>
  )
}
