import { EvidenceLiveFeed } from './EvidenceLiveFeed'
import { Stepper } from './Stepper'
import { StatusPill } from './StatusPill'

export function DiscoverJourneysPlaceholder({
  discoveryStatus,
  discoveryFailureReason,
  discoveryRunId,
}: {
  discoveryStatus: string
  discoveryFailureReason: string | null
  discoveryRunId: string
}) {
  const sessionExpired = discoveryStatus === 'failed' && discoveryFailureReason === 'session_expired'

  return (
    <>
      <Stepper current="discover" />
      <main
        style={{
          maxWidth: 'var(--content-max)',
          margin: '0 auto',
          padding: `var(--content-top) var(--content-x)`,
        }}
      >
        <div style={{ display: 'flex', alignItems: 'center', gap: 'var(--space-3)', margin: '0 0 8px' }}>
          <h1 style={{ fontSize: 19, fontWeight: 650, margin: 0 }}>Discover Journeys</h1>
          <StatusPill status={discoveryStatus} />
        </div>

        {sessionExpired ? (
          <p className="caption" role="alert" style={{ color: 'var(--danger)' }}>
            Session expired mid-crawl. Re-authenticate to continue discovery.
          </p>
        ) : discoveryStatus === 'failed' ? (
          <p className="caption" role="alert" style={{ color: 'var(--danger)' }}>
            Discovery Run failed.
          </p>
        ) : (
          <p className="caption">
            Discovery Run status is tracked here as it runs; the Journey list itself is built out
            in a later story.
          </p>
        )}

        <EvidenceLiveFeed discoveryRunId={discoveryRunId} active={discoveryStatus === 'running'} />
      </main>
    </>
  )
}
