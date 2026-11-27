import { createPortal } from 'react-dom'
import { useRef, useState } from 'react'
import { FontAwesomeIcon } from '@fortawesome/react-fontawesome'
import { faXmark } from '@fortawesome/free-solid-svg-icons'
import { ApiError, api, type Role } from '../api'
import { FieldError } from './environments/EnvironmentModal'
import { LoadingDots } from './LoadingDots'
import { modalButton, modalCloseButton, modalFooter, modalHeader, modalOverlay, modalPanel, modalTitle } from './modalStyles'
import { useEscapeToClose } from '../hooks/useEscapeToClose'

// Shared by this invite modal and Team members' "Change role" picker.
export const ROLE_OPTIONS: { key: Role; label: string; hint: string }[] = [
  {
    key: 'standard_user',
    label: 'User',
    hint: 'Can onboard applications, review scenarios and trigger runs.',
  },
  {
    key: 'super_admin',
    label: 'Super Admin',
    hint: 'Everything a user can do, plus saved credentials and Explorer limits.',
  },
]

const EMAIL_RE = /^[^\s@]+@[^\s@]+\.[^\s@]{2,}$/

export function InviteTeammateModal({ onClose }: { onClose: () => void }) {
  useEscapeToClose(onClose)
  const [email, setEmail] = useState('')
  const [role, setRole] = useState<Role>('standard_user')
  const [error, setError] = useState<string | null>(null)
  const [sent, setSent] = useState(false)
  const [submitting, setSubmitting] = useState(false)
  const [touched, setTouched] = useState(false)
  const inputRef = useRef<HTMLInputElement>(null)
  const clean = email.trim()
  const emailInvalid = touched && !EMAIL_RE.test(clean)

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault()
    setError(null)
    if (!EMAIL_RE.test(clean)) {
      setTouched(true)
      inputRef.current?.focus()
      return
    }
    setSubmitting(true)
    try {
      await api.sendInvite({ email: clean, role })
      setSent(true)
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'Could not send invite.')
    } finally {
      setSubmitting(false)
    }
  }

  // Portaled to <body>: a card with `backdrop-filter` becomes the containing
  // block of `position: fixed`, which would trap the overlay inside it.
  return createPortal(
    <div style={{ ...modalOverlay, zIndex: 90 }}>
      <form noValidate onSubmit={handleSubmit} style={{ ...modalPanel, maxWidth: 520 }}>
        <div style={modalHeader}>
          <h2 style={modalTitle}>Invite user</h2>
          {!sent && (
            <button type="button" aria-label="Close" onClick={onClose} style={modalCloseButton}>
              <FontAwesomeIcon icon={faXmark} />
            </button>
          )}
        </div>

        {sent ? (
          <>
            <div style={{ padding: '4px 28px 22px' }}>
              <p style={{ fontSize: 13.5, color: 'var(--fg-3)', margin: 0 }}>Invite sent to {clean}.</p>
            </div>
            <div style={modalFooter}>
              <button type="button" className="button-primary" onClick={onClose} style={modalButton}>
                Done
              </button>
            </div>
          </>
        ) : (
          <>
            <fieldset disabled={submitting} style={{ border: 0, margin: 0, padding: 0, display: 'contents' }}>
              <div style={{ flex: 1, minHeight: 0, overflowY: 'auto', display: 'flex', flexDirection: 'column', gap: 18, padding: '4px 28px 22px' }}>
                <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
                  <span style={{ fontSize: 10.5, fontWeight: 600, letterSpacing: '0.07em', textTransform: 'uppercase', color: 'var(--fg-4)' }}>Email address</span>
                  <div
                    className="field-shell"
                    style={{
                      display: 'flex',
                      alignItems: 'center',
                      gap: 10,
                      height: 42,
                      padding: '0 13px',
                      borderRadius: 10,
                      border: emailInvalid ? '1px solid var(--danger)' : '1px solid var(--border-2)',
                      background: 'var(--panel)',
                      boxShadow: 'inset 0 1px 2px rgba(16,20,30,0.04)',
                    }}
                  >
                    <input
                      ref={inputRef}
                      type="email"
                      inputMode="email"
                      autoComplete="off"
                      aria-invalid={emailInvalid}
                      autoFocus
                      data-bare
                      placeholder="Enter their email"
                      value={email}
                      onChange={(e) => setEmail(e.target.value)}
                      onBlur={() => setTouched(clean !== '')}
                      style={{
                        flex: 1,
                        minWidth: 0,
                        height: '100%',
                        border: 'none',
                        background: 'transparent',
                        outline: 'none',
                        color: 'var(--fg-1)',
                        fontFamily: 'var(--font-mono)',
                        fontSize: 13,
                        letterSpacing: '-0.01em',
                      }}
                    />
                  </div>
                  {emailInvalid && <FieldError>Enter a valid email address</FieldError>}
                </div>

                <div style={{ display: 'flex', flexDirection: 'column', gap: 9 }}>
                  <span style={{ fontSize: 10.5, fontWeight: 600, letterSpacing: '0.07em', textTransform: 'uppercase', color: 'var(--fg-4)' }}>Role</span>
                  <div role="radiogroup" aria-label="Role" style={{ display: 'grid', gridTemplateColumns: 'repeat(2, minmax(0, 1fr))', gap: 10 }}>
                    {ROLE_OPTIONS.map((r) => {
                      const active = role === r.key
                      return (
                        <label
                          key={r.key}
                          style={{
                            display: 'flex',
                            alignItems: 'center',
                            gap: 10,
                            height: 44,
                            padding: '0 14px',
                            borderRadius: 10,
                            border: active ? '1px solid rgba(30,150,138,0.4)' : '1px solid var(--border-2)',
                            background: active ? 'rgba(30,150,138,0.08)' : 'var(--panel)',
                            cursor: 'pointer',
                          }}
                        >
                          <input
                            type="radio"
                            name="invite-role"
                            checked={active}
                            onChange={() => setRole(r.key)}
                            style={{ position: 'absolute', opacity: 0, pointerEvents: 'none' }}
                          />
                          <span
                            aria-hidden="true"
                            style={{
                              width: 16,
                              height: 16,
                              flex: 'none',
                              borderRadius: 1000,
                              border: active ? '5px solid var(--accent-2)' : '1px solid var(--border-2)',
                              background: 'var(--panel)',
                              boxSizing: 'border-box',
                            }}
                          />
                          <span style={{ fontSize: 13.5, fontWeight: 600, color: 'var(--fg-1)' }}>{r.label}</span>
                        </label>
                      )
                    })}
                  </div>
                </div>

                {error && (
                  <div style={{ color: 'var(--bad)', fontSize: 13 }} role="alert">
                    {error}
                  </div>
                )}
              </div>
            </fieldset>

            <div style={{ ...modalFooter, justifyContent: 'flex-end' }}>
              <div style={{ display: 'flex', gap: 10 }}>
                <button type="button" className="button-secondary" onClick={onClose} style={modalButton}>
                  Cancel
                </button>
                <button
                  type="submit"
                  className="button-primary"
                  disabled={submitting}
                  style={{ ...modalButton, cursor: submitting ? 'default' : 'pointer', opacity: submitting ? 0.75 : 1 }}
                >
                  {submitting ? <LoadingDots label="Sending" /> : 'Send invite'}
                </button>
              </div>
            </div>
          </>
        )}
      </form>
    </div>,
    document.body,
  )
}
