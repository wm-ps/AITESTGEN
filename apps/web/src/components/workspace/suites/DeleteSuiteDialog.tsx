import { useState } from 'react'
import {
  ApiError,
  SUITE_HAS_RUNS,
  SUITE_HAS_SCHEDULES,
  SUITE_RUN_IN_PROGRESS,
  api,
  type CollectionSummary,
} from '../../../api'
import { LoadingDots } from '../../LoadingDots'
import { SuiteModal, plural } from './SuiteModal'

// Deleting a suite never touches its test cases. If it has runs, the user is
// told those runs are removed too, and Cancel deletes nothing.
export function DeleteSuiteDialog({
  applicationId,
  suite,
  onClose,
  onDeleted,
}: {
  applicationId: string
  suite: CollectionSummary
  onClose: () => void
  onDeleted: () => void
}) {
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const hasRuns = suite.run_count > 0

  async function confirm() {
    if (busy) return
    setBusy(true)
    setError(null)
    try {
      await api.deleteCollection(suite.id, hasRuns)
      onDeleted()
    } catch (err) {
      const code = err instanceof ApiError ? err.message : ''
      if (code === SUITE_HAS_SCHEDULES) {
        // Name the schedules that use it, so the user knows which to change.
        const schedules = await api.listSchedules(applicationId).catch(() => [])
        const names = schedules.filter((s) => s.test_collection_id === suite.id).map((s) => s.name)
        setError(
          names.length > 0
            ? `This suite is used by ${names.join(', ')}. Change or delete ${names.length === 1 ? 'that schedule' : 'those schedules'} first.`
            : 'This suite is used by a schedule. Change or delete that schedule first.',
        )
        setBusy(false)
        return
      }
      setError(
        code === SUITE_RUN_IN_PROGRESS
          ? 'A run of this suite is still in progress. Wait for it to finish or stop it first.'
          : code === SUITE_HAS_RUNS
            ? 'This suite has new runs. Close this dialog and try again.'
            : 'Could not delete the suite. Try again.',
      )
      setBusy(false)
    }
  }

  return (
    <SuiteModal
      title={`Delete “${suite.name}”?`}
      ariaLabel="Delete test suite"
      onClose={onClose}
      maxWidth={460}
      footer={
        <>
          <span />
          <div style={{ display: 'flex', gap: 10 }}>
            <button type="button" className="button-secondary" onClick={onClose} style={{ padding: '10px 22px', fontSize: 14 }}>
              Cancel
            </button>
            <button
              type="button"
              className="button-primary"
              aria-disabled={busy}
              onClick={confirm}
              style={{ padding: '10px 22px', fontSize: 14, background: 'var(--danger)', opacity: busy ? 0.65 : 1 }}
            >
              {busy ? <LoadingDots label="Deleting" /> : hasRuns ? 'Delete suite and runs' : 'Delete suite'}
            </button>
          </div>
        </>
      }
    >
      <div style={{ padding: '4px 28px 22px', fontSize: 13.5, color: 'var(--fg-2)', lineHeight: 1.5 }}>
        {hasRuns ? (
          <p style={{ margin: 0 }}>
            This suite has {plural(suite.run_count, 'run')}. Deleting it also permanently removes{' '}
            {suite.run_count === 1 ? 'that run' : 'those runs'} from Test runs. Your test cases are not affected.
          </p>
        ) : (
          <p style={{ margin: 0 }}>Your test cases are not affected.</p>
        )}
        {error && (
          <p role="alert" style={{ margin: '12px 0 0', fontSize: 12.5, color: 'var(--danger)' }}>
            {error}
          </p>
        )}
      </div>
    </SuiteModal>
  )
}
