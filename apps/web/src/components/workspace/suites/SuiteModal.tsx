import type { ReactNode } from 'react'
import { FontAwesomeIcon } from '@fortawesome/react-fontawesome'
import { faXmark } from '@fortawesome/free-solid-svg-icons'
import { useEscapeToClose } from '../../../hooks/useEscapeToClose'
import { modalCloseButton, modalFooter, modalHeader, modalOverlay, modalPanel, modalTitle } from '../../modalStyles'

// The overlay + card-panel modal every Test suites dialog shares — same shape
// as RunJourneysDialog.tsx / ScheduleDialog.tsx. `footer` sits on the tinted
// bar at the bottom; `bodyScrolls` is false for the two-pane picker, which
// scrolls its panes itself.
export function SuiteModal({
  title,
  subtitle,
  ariaLabel,
  onClose,
  maxWidth = 480,
  footer,
  bodyScrolls = true,
  children,
}: {
  title: string
  subtitle?: string
  ariaLabel?: string
  onClose: () => void
  maxWidth?: number
  footer?: ReactNode
  bodyScrolls?: boolean
  children: ReactNode
}) {
  useEscapeToClose(onClose)
  return (
    <div onClick={onClose} style={modalOverlay}>
      <div
        role="dialog"
        aria-modal="true"
        aria-label={ariaLabel ?? title}
        onClick={(e) => e.stopPropagation()}
        style={{ ...modalPanel, maxWidth }}
      >
        <div style={{ ...modalHeader, borderBottom: subtitle || !bodyScrolls ? '1px solid var(--line)' : undefined }}>
          <div>
            <h2 style={modalTitle}>{title}</h2>
            {subtitle && <p className="caption" style={{ margin: '4px 0 0', fontSize: 13 }}>{subtitle}</p>}
          </div>
          <button type="button" aria-label="Close" onClick={onClose} style={modalCloseButton}>
            <FontAwesomeIcon icon={faXmark} />
          </button>
        </div>
        <div
          style={{
            flex: 1,
            minHeight: 0,
            overflowY: bodyScrolls ? 'auto' : 'hidden',
            display: 'flex',
            flexDirection: 'column',
          }}
        >
          {children}
        </div>
        {footer && (
          <div style={{ ...modalFooter, justifyContent: 'space-between' }}>{footer}</div>
        )}
      </div>
    </div>
  )
}

export const plural = (n: number, word: string) => `${n} ${word}${n === 1 ? '' : 's'}`

// The amber "N unavailable" chip used on the suites list, the suite header and
// the Run test suite dialog.
export function UnavailableBadge({ count }: { count: number }) {
  if (count <= 0) return null
  return (
    <span
      style={{
        flex: 'none',
        fontSize: 11.5,
        fontWeight: 600,
        padding: '2px 10px',
        borderRadius: 999,
        background: 'var(--warn-wash)',
        color: 'var(--warn-strong)',
        whiteSpace: 'nowrap',
      }}
    >
      {count} unavailable
    </span>
  )
}
