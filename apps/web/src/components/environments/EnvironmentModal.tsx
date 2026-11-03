import type { IconDefinition } from '@fortawesome/fontawesome-svg-core'
import { FontAwesomeIcon } from '@fortawesome/react-fontawesome'
import { faXmark } from '@fortawesome/free-solid-svg-icons'
import { useEscapeToClose } from '../../hooks/useEscapeToClose'
import { LoadingDots } from '../LoadingDots'

// The overlay + card shell every environment dialog shares — same look as
// ScheduleDialog (icon tile, title + one-line subtitle, close button, footer).
export function EnvironmentModal({
  title,
  subtitle,
  icon,
  onClose,
  onSubmit,
  children,
  footer,
  tone = 'accent',
  maxWidth = 460,
}: {
  title: string
  subtitle?: string
  icon: IconDefinition
  onClose: () => void
  onSubmit?: (event: React.FormEvent) => void
  children: React.ReactNode
  footer: React.ReactNode
  tone?: 'accent' | 'danger'
  maxWidth?: number
}) {
  useEscapeToClose(onClose)
  const iconStyle =
    tone === 'danger'
      ? { background: 'var(--bad-wash, #fde8ec)', color: 'var(--bad)' }
      : {
          background: 'linear-gradient(160deg,var(--accent),var(--accent-deep))',
          color: '#fff',
          boxShadow: 'var(--accent-glow)',
        }
  const Shell = onSubmit ? 'form' : 'div'

  return (
    <div
      onClick={onClose}
      style={{
        position: 'fixed',
        inset: 0,
        zIndex: 90,
        background: 'rgba(10,12,16,0.46)',
        backdropFilter: 'blur(3px)',
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
        padding: 24,
      }}
    >
      <Shell
        role="dialog"
        aria-modal="true"
        aria-label={title}
        noValidate={onSubmit ? true : undefined}
        onClick={(e: React.MouseEvent) => e.stopPropagation()}
        onSubmit={onSubmit}
        style={{
          width: '100%',
          maxWidth,
          position: 'relative',
          background: 'linear-gradient(180deg,rgba(255,255,255,0.96),rgba(255,255,255,0.82))',
          backdropFilter: 'blur(20px) saturate(1.3)',
          border: '1px solid var(--border)',
          borderRadius: 16,
          boxShadow: '0 30px 80px rgba(8,12,20,0.34), var(--panel-shadow)',
          maxHeight: 'calc(100vh - 48px)',
          overflowY: 'auto',
          boxSizing: 'border-box',
        }}
      >
        <div style={{ display: 'flex', alignItems: 'flex-start', gap: 13, padding: '22px 22px 18px', borderBottom: '1px solid var(--line)' }}>
          <div
            style={{
              width: 38,
              height: 38,
              flex: 'none',
              borderRadius: 11,
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
              ...iconStyle,
            }}
          >
            <FontAwesomeIcon icon={icon} style={{ fontSize: 14 }} />
          </div>
          <div style={{ flex: 1, minWidth: 0 }}>
            <div style={{ fontSize: 16, fontWeight: 600, color: 'var(--fg)', letterSpacing: '-0.015em' }}>{title}</div>
            {subtitle && <div style={{ fontSize: 12.5, color: 'var(--fg-3)', marginTop: 3 }}>{subtitle}</div>}
          </div>
          <button
            type="button"
            aria-label="Close"
            onClick={onClose}
            style={{ width: 28, height: 28, flex: 'none', border: 'none', background: 'transparent', borderRadius: 8, display: 'flex', alignItems: 'center', justifyContent: 'center', color: 'var(--fg-4)', cursor: 'pointer' }}
          >
            <FontAwesomeIcon icon={faXmark} style={{ fontSize: 13 }} />
          </button>
        </div>
        <div style={{ display: 'flex', flexDirection: 'column', gap: 16, padding: '20px 22px 8px' }}>{children}</div>
        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'flex-end', gap: 10, padding: '14px 22px 20px' }}>{footer}</div>
      </Shell>
    </div>
  )
}

const buttonBase: React.CSSProperties = {
  display: 'inline-flex',
  alignItems: 'center',
  gap: 8,
  height: 36,
  padding: '0 18px',
  borderRadius: 9,
  fontSize: 13,
  whiteSpace: 'nowrap',
  flex: 'none',
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
  icon,
  danger = false,
  type = 'submit',
  onSubmit,
}: {
  onCancel: () => void
  submitLabel: string
  busyLabel: string
  busy: boolean
  disabled?: boolean
  icon?: IconDefinition
  danger?: boolean
  type?: 'submit' | 'button'
  onSubmit?: () => void
}) {
  const blocked = busy || disabled
  return (
    <>
      <button
        type="button"
        onClick={onCancel}
        style={{ ...buttonBase, border: '1px solid var(--border-2)', background: 'var(--panel)', color: 'var(--fg-2)', fontWeight: 500, cursor: 'pointer' }}
      >
        Cancel
      </button>
      <button
        type={type}
        onClick={type === 'button' ? onSubmit : undefined}
        disabled={blocked}
        style={{
          ...buttonBase,
          border: 'none',
          background: danger ? 'var(--bad)' : 'var(--accent)',
          color: '#fff',
          fontWeight: 600,
          cursor: blocked ? 'not-allowed' : 'pointer',
          opacity: disabled && !busy ? 0.6 : 1,
          boxShadow: danger ? 'none' : 'var(--accent-glow)',
        }}
      >
        {busy ? (
          <LoadingDots label={busyLabel} />
        ) : (
          <>
            {icon && <FontAwesomeIcon icon={icon} style={{ fontSize: 11 }} />}
            {submitLabel}
          </>
        )}
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
