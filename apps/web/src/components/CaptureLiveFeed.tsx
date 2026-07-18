import { useEffect, useState } from 'react'
import { api, type CaptureRead } from '../api'

const POLL_INTERVAL_MS = 1500

export function CaptureLiveFeed({
  discoveryRunId,
  active,
}: {
  discoveryRunId: string
  active: boolean
}) {
  const [captures, setCaptures] = useState<CaptureRead[]>([])

  useEffect(() => {
    let cancelled = false

    async function poll() {
      try {
        const rows = await api.listCaptures(discoveryRunId)
        if (!cancelled) setCaptures(rows)
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

  if (captures.length === 0) return null

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
        {captures.map((item, index) => (
          <li
            key={`${item.created_at}-${index}`}
            style={{ fontFamily: 'var(--font-mono)', fontSize: 12.5, color: 'var(--ink-muted)' }}
          >
            [{item.kind}] {item.summary}
          </li>
        ))}
      </ul>
    </div>
  )
}
