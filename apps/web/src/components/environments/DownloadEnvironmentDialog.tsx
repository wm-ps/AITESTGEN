import { useState } from 'react'
import { api } from '../../api'
import { EnvironmentModal, FieldError, ModalActions } from './EnvironmentModal'
import { EnvironmentSelect } from './EnvironmentSelect'

// "Download project" opens this first: the Playwright project is built for
// the environment picked here (its base URL and login URL are written into the
// config; sign-in details never are — they come from environment variables,
// as the README says).
export function DownloadEnvironmentDialog({
  applicationId,
  onClose,
}: {
  applicationId: string
  onClose: () => void
}) {
  const [environmentId, setEnvironmentId] = useState<string | null>(null)
  const [downloading, setDownloading] = useState(false)
  const [error, setError] = useState<string | null>(null)

  async function handleDownload() {
    setError(null)
    setDownloading(true)
    try {
      await api.downloadTestSuiteProject(applicationId, environmentId ?? undefined)
      onClose()
    } catch {
      setError('Could not download the project. Try again.')
      setDownloading(false)
    }
  }

  return (
    <EnvironmentModal
      title="Download project"
      subtitle="Choose the environment the Playwright project should be configured for. Its base URL and login URL are written into the config."
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
      <EnvironmentSelect value={environmentId} onChange={setEnvironmentId} />
      {error && <FieldError>{error}</FieldError>}
    </EnvironmentModal>
  )
}
