import type { ReactNode } from 'react'
import { FontAwesomeIcon } from '@fortawesome/react-fontawesome'
import { faXmark } from '@fortawesome/free-solid-svg-icons'
import { useEscapeToClose } from '../../../hooks/useEscapeToClose'

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
    <div
      onClick={onClose}
      style={{
        position: 'fixed',
        inset: 0,
        background: 'rgba(15,23,42,0.35)',
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
        padding: 16,
        zIndex: 50,
      }}
    >
      <div
        role="dialog"
        aria-modal="true"
        aria-label={ariaLabel ?? title}
        onClick={(e) => e.stopPropagation()}
        style={{
          background: 'var(--panel)',
          border: '1px solid var(--border-2)',
          borderRadius: 16,
          boxShadow: '0 30px 80px rgba(8,12,20,0.34), var(--panel-shadow)',
          width: '100%',
          maxWidth,
          maxHeight: '86vh',
          display: 'flex',
          flexDirection: 'column',
          overflow: 'hidden',
          boxSizing: 'border-box',
        }}
      >
        <div
          style={{
            display: 'flex',
            alignItems: 'flex-start',
            justifyContent: 'space-between',
            gap: 12,
            padding: '20px 28px 16px',
            borderBottom: subtitle || !bodyScrolls ? '1px solid var(--line)' : undefined,
          }}
        >
          <div>
            <h2 style={{ fontSize: 17, fontWeight: 600, color: 'var(--fg)', margin: 0 }}>{title}</h2>
            {subtitle && <p className="caption" style={{ margin: '4px 0 0', fontSize: 13 }}>{subtitle}</p>}
          </div>
          <button
            type="button"
            aria-label="Close"
            onClick={onClose}
            style={{ background: 'none', border: 'none', cursor: 'pointer', color: 'var(--fg-3)', padding: 4 }}
          >
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
          <div
            style={{
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'space-between',
              gap: 12,
              padding: '16px 28px',
              background: 'var(--bg-2)',
              borderTop: '1px solid var(--line)',
            }}
          >
            {footer}
          </div>
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
