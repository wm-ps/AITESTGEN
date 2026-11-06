import { useState } from 'react'
import { ApiError, COLLECTION_EMPTY, api } from '../../api'
import { SuiteSelect } from '../workspace/suites/SuiteSelect'
import { EnvironmentModal, FieldError, ModalActions } from './EnvironmentModal'
import { EnvironmentSelect } from './EnvironmentSelect'

// "Download project" opens this first: the Playwright project is built for the
// test suite and environment picked here. "All test cases" (the default) is the
// whole project; a suite narrows it to that suite's tests. The environment's
// base URL and login URL are written into the config; sign-in details never
// are — they come from environment variables, as the README says.
export function DownloadEnvironmentDialog({
  applicationId,
  onClose,
}: {
  applicationId: string
  onClose: () => void
}) {
  const [environmentId, setEnvironmentId] = useState<string | null>(null)
  const [testCollectionId, setTestCollectionId] = useState<string | null>(null)
  const [downloading, setDownloading] = useState(false)
  const [error, setError] = useState<string | null>(null)

  async function handleDownload() {
    setError(null)
    setDownloading(true)
    try {
      await api.downloadTestSuiteProject(applicationId, environmentId ?? undefined, testCollectionId ?? undefined)
      onClose()
    } catch (err) {
      setError(
        err instanceof ApiError && err.message === COLLECTION_EMPTY
          ? 'This test suite has no test cases to download.'
          : 'Could not download the project. Try again.',
      )
      setDownloading(false)
    }
  }

  return (
    <EnvironmentModal
      title="Download project"
      subtitle="Choose which test cases and which environment the Playwright project is built for. The environment's base URL and login URL are written into the config."
      maxWidth={440}
      onClose={onClose}
      footer={
        <ModalActions
          type="button"
          onSubmit={handleDownload}
          onCancel={onClose}
          submitLabel="Download"
          busyLabel="Downloading"
          busy={downloading}
        />
      }
    >
      <SuiteSelect applicationId={applicationId} value={testCollectionId} onChange={setTestCollectionId} />
      <EnvironmentSelect value={environmentId} onChange={setEnvironmentId} />
      {error && <FieldError>{error}</FieldError>}
    </EnvironmentModal>
  )
}
