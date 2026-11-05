import type { IconDefinition } from '@fortawesome/fontawesome-svg-core'
import { FontAwesomeIcon } from '@fortawesome/react-fontawesome'
import { faXmark } from '@fortawesome/free-solid-svg-icons'
import { useEscapeToClose } from '../../hooks/useEscapeToClose'
import { LoadingDots } from '../LoadingDots'
import {
  modalButton,
  modalCloseButton,
  modalFooter,
  modalHeader,
  modalOverlay,
  modalPanel,
  modalTitle,
} from '../modalStyles'

// The overlay + card shell every environment dialog shares — same look as the
// Test suites dialogs (SuiteModal): title + one-line subtitle, plain close
// button, tinted footer. `icon` and `tone` are accepted so callers don't
// change, but dialogs no longer draw an icon tile.
export function EnvironmentModal({
  title,
  subtitle,
  onClose,
  onSubmit,
  children,
  footer,
  maxWidth = 460,
}: {
  title: string
  subtitle?: string
  icon?: IconDefinition
  onClose: () => void
  onSubmit?: (event: React.FormEvent) => void
  children: React.ReactNode
  footer: React.ReactNode
  tone?: 'accent' | 'danger'
  maxWidth?: number
}) {
  useEscapeToClose(onClose)
  const Shell = onSubmit ? 'form' : 'div'

  return (
    <div onClick={onClose} style={{ ...modalOverlay, zIndex: 90 }}>
      <Shell
        role="dialog"
        aria-modal="true"
        aria-label={title}
        noValidate={onSubmit ? true : undefined}
        onClick={(e: React.MouseEvent) => e.stopPropagation()}
        onSubmit={onSubmit}
        style={{ ...modalPanel, maxWidth }}
      >
        <div style={modalHeader}>
          <div>
            <h2 style={modalTitle}>{title}</h2>
            {subtitle && <p className="caption" style={{ margin: '4px 0 0', fontSize: 13 }}>{subtitle}</p>}
          </div>
          <button type="button" aria-label="Close" onClick={onClose} style={modalCloseButton}>
            <FontAwesomeIcon icon={faXmark} />
          </button>
        </div>
        <div style={{ flex: 1, minHeight: 0, overflowY: 'auto', display: 'flex', flexDirection: 'column', gap: 16, padding: '4px 28px 22px' }}>
          {children}
        </div>
        <div style={modalFooter}>{footer}</div>
      </Shell>
    </div>
  )
}

// Cancel + the primary action. While `busy` the primary shows its label with
// trailing bouncing dots (`busyLabel`, no "…") and Cancel stays available —
// closing the dialog abandons the work and saves nothing.
export function ModalActions({
  onCancel,
  submitLabel,
  busyLabel,
  busy,
  disabled = false,
  danger = false,
  type = 'submit',
  onSubmit,
}: {
  onCancel: () => void
  submitLabel: string
  busyLabel: string
  busy: boolean
  disabled?: boolean
  icon?: IconDefinition // accepted for callers; buttons are text-only
  danger?: boolean
  type?: 'submit' | 'button'
  onSubmit?: () => void
}) {
  const blocked = busy || disabled
  return (
    <>
      <button type="button" className="button-secondary" onClick={onCancel} style={modalButton}>
        Cancel
      </button>
      <button
        type={type}
        className="button-primary"
        onClick={type === 'button' ? onSubmit : undefined}
        disabled={blocked}
        style={{
          ...modalButton,
          ...(danger ? { background: 'var(--danger)' } : null),
          cursor: blocked ? 'not-allowed' : 'pointer',
          opacity: disabled && !busy ? 0.6 : 1,
        }}
      >
        {busy ? <LoadingDots label={busyLabel} /> : submitLabel}
      </button>
    </>
  )
}

export function FieldError({ children }: { children: React.ReactNode }) {
  return (
    <div role="alert" style={{ color: 'var(--danger)', fontSize: 13 }}>
      {children}
    </div>
  )
}
