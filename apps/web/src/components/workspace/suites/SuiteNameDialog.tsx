import { useState } from 'react'
import { ApiError, COLLECTION_NAME_TAKEN } from '../../../api'
import { LoadingDots } from '../../LoadingDots'
import { SuiteModal } from './SuiteModal'

const MAX_LENGTH = 60

// Name a new suite, or rename an existing one. `onSubmit` throws an ApiError
// on failure; a name that is already used (case-insensitively) is shown in
// place so the user can fix it without losing the dialog.
export function SuiteNameDialog({
  title,
  initialName = '',
  submitLabel,
  busyLabel,
  onSubmit,
  onClose,
}: {
  title: string
  initialName?: string
  submitLabel: string
  busyLabel: string
  onSubmit: (name: string) => Promise<void>
  onClose: () => void
}) {
  const [name, setName] = useState(initialName)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const trimmed = name.trim()

  async function submit() {
    if (busy) return
    if (!trimmed) {
      setError('Enter a suite name to continue')
      return
    }
    setBusy(true)
    setError(null)
    try {
      await onSubmit(trimmed)
    } catch (err) {
      setError(
        err instanceof ApiError && err.message === COLLECTION_NAME_TAKEN
          ? 'A suite with this name already exists'
          : 'Could not save the suite. Try again.',
      )
      setBusy(false)
    }
  }

  return (
    <SuiteModal
      title={title}
      onClose={onClose}
      maxWidth={440}
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
              onClick={submit}
              style={{ padding: '10px 22px', fontSize: 14, opacity: busy ? 0.65 : 1 }}
            >
              {busy ? <LoadingDots label={busyLabel} /> : submitLabel}
            </button>
          </div>
        </>
      }
    >
      <div style={{ padding: '4px 28px 22px' }}>
        <label className="field">
          <span className="label-required" style={{ fontSize: 13.5, fontWeight: 600, color: 'var(--fg)' }}>
            Suite name
          </span>
          <input
            autoFocus
            maxLength={MAX_LENGTH}
            placeholder="Enter the suite name"
            value={name}
            aria-invalid={error !== null}
            style={error ? { borderColor: 'var(--danger)' } : undefined}
            onChange={(e) => {
              setName(e.target.value)
              if (error) setError(null)
            }}
            onKeyDown={(e) => {
              if (e.key === 'Enter') void submit()
            }}
          />
        </label>
        {error && (
          <p role="alert" style={{ margin: '8px 0 0', fontSize: 12.5, color: 'var(--danger)' }}>
            {error}
          </p>
        )}
      </div>
    </SuiteModal>
  )
}
