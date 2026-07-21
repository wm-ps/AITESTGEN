import { useEffect, useState } from 'react'
import { api } from '../api'

const POLL_INTERVAL_MS = 1500

// Closes a real gap: `discoveryStatus`/`discoveryStage`/`discoveryFailureReason`
// were previously static props frozen at Application-creation time — nothing
// re-fetched them, so the status pill/session-expired banner never updated
// without a page reload (Story 2.7, sprint-change-proposal-2026-07-21 CR-2).
export function useDiscoveryProgress(
  applicationId: string,
  initialStatus: string,
  initialStage: string | null,
  initialFailureReason: string | null,
  hasJourneys: boolean,
) {
  const [status, setStatus] = useState(initialStatus)
  const [stage, setStage] = useState(initialStage)
  const [failureReason, setFailureReason] = useState(initialFailureReason)

  useEffect(() => {
    // `status` flips to "complete" as soon as the crawl finishes — well
    // before Analysis (stage=analyzing) runs — so gating on `hasJourneys`
    // (not `status !== 'running'`) is what keeps progress visible through
    // the whole pipeline, not just the crawl.
    if (hasJourneys || status === 'failed') return

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
    }

    poll()
    const interval = setInterval(poll, POLL_INTERVAL_MS)
    return () => {
      cancelled = true
      clearInterval(interval)
    }
  }, [applicationId, hasJourneys, status])

  return { status, stage, failureReason }
}
