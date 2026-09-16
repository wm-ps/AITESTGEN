import { useEffect, useState } from 'react'
import { api } from '../api'

const POLL_INTERVAL_MS = 3000

// Closes a real gap: `discoveryStatus`/`discoveryStage`/`discoveryFailureReason`
// were previously static props frozen at Application-creation time — nothing
// re-fetched them, so the status pill/session-expired banner never updated
// without a page reload (Story 2.7, sprint-change-proposal-2026-07-21 CR-2).
export function useDiscoveryProgress(
  applicationId: string,
  initialStatus: string,
  initialStage: string | null,
  initialFailureReason: string | null,
) {
  const [status, setStatus] = useState(initialStatus)
  const [stage, setStage] = useState(initialStage)
  const [failureReason, setFailureReason] = useState(initialFailureReason)
  const [workerAvailable, setWorkerAvailable] = useState(true)
  const [retryCount, setRetryCount] = useState(0)

  useEffect(() => {
    // Stop only on the two real terminal states. Used to also stop as soon
    // as the first Journey existed — but InferenceActivity can still fail
    // after writing Journey #1, and that stopped condition meant the UI
    // never learned about it (stuck showing "running" forever). "analyzed"
    // is the same terminal marker DiscoverJourneys.tsx's own poll waits for.
    if (stage === 'analyzed' || status === 'failed') return

    let cancelled = false

    async function poll() {
      try {
        const application = await api.getApplication(applicationId)
        if (cancelled) return
        setStatus(application.discovery_status)
        setStage(application.discovery_stage)
        setFailureReason(application.discovery_failure_reason ?? null)
      } catch {
        // best-effort poll — a transient failure just skips this tick
      }
      // `start_discovery_run` only checks for a live worker before starting
      // — a worker that crashes right after leaves status="running" with
      // nothing to explain why it's stuck. Only worth asking while running;
      // any other status already carries its own terminal reason.
      if (status === 'running') {
        try {
          const { available, retry_count } = await api.getDiscoveryStatus(applicationId)
          if (!cancelled) {
            setWorkerAvailable(available)
            setRetryCount(retry_count)
          }
        } catch {
          // best-effort poll — a transient failure just skips this tick
        }
      }
    }

    poll()
    const interval = setInterval(poll, POLL_INTERVAL_MS)
    return () => {
      cancelled = true
      clearInterval(interval)
    }
  }, [applicationId, stage, status])

  return { status, stage, failureReason, workerAvailable, retryCount }
}
