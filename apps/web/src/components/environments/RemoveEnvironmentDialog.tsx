import { useState } from 'react'
import { ApiError, api, type EnvironmentRead } from '../../api'
import { EnvironmentModal, FieldError, ModalActions } from './EnvironmentModal'

const IN_USE_MESSAGE = "This environment has test runs or schedules, so it can't be removed."

export function RemoveEnvironmentDialog({
  applicationId,
  environment,
  onClose,
  onRemoved,
}: {
  applicationId: string
  environment: EnvironmentRead
  onClose: () => void
  onRemoved: () => void
}) {
  const [removing, setRemoving] = useState(false)
  const [error, setError] = useState<string | null>(null)

  async function handleRemove() {
    setError(null)
    setRemoving(true)
    try {
      await api.deleteEnvironment(applicationId, environment.id as string)
      onRemoved()
    } catch (err) {
      setError(
        err instanceof ApiError && err.message === 'ENVIRONMENT_IN_USE'
          ? IN_USE_MESSAGE
          : err instanceof ApiError
            ? err.message
            : 'Could not remove this environment.',
      )
      setRemoving(false)
    }
  }

  return (
    <EnvironmentModal
      title={`Remove ${environment.name} environment?`}
      maxWidth={420}
      onClose={onClose}
      footer={
        <ModalActions
          type="button"
          onSubmit={handleRemove}
          onCancel={onClose}
          submitLabel="OK, remove"
          busyLabel="Removing"
          busy={removing}
          danger
        />
      }
    >
      <p style={{ margin: 0, fontSize: 13.5, lineHeight: 1.5, color: 'var(--fg-3)' }}>
        Are you sure you want to remove the {environment.name} environment? Your test cases are kept, but you won't be able
        to run them against it.
      </p>
      {error && <FieldError>{error}</FieldError>}
    </EnvironmentModal>
  )
}
