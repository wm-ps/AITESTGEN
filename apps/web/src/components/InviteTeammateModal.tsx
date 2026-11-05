import { useState } from 'react'
import { FontAwesomeIcon } from '@fortawesome/react-fontawesome'
import { faXmark } from '@fortawesome/free-solid-svg-icons'
import { ApiError, api, type Role } from '../api'
import { LoadingDots } from './LoadingDots'
import { modalButton, modalCloseButton, modalFooter, modalHeader, modalOverlay, modalPanel, modalTitle } from './modalStyles'
import { useEscapeToClose } from '../hooks/useEscapeToClose'

// Shared by this invite modal and Team members' "Change role" picker.
export const ROLE_OPTIONS: { key: Role; label: string; hint: string }[] = [
  {
    key: 'member',
    label: 'Member',
    hint: 'Can onboard applications, review scenarios and trigger runs.',
  },
  {
    key: 'admin',
    label: 'Admin',
    hint: 'Everything a member can do, plus saved credentials and Explorer limits.',
  },
  {
    key: 'viewer',
    label: 'Viewer',
    hint: 'Can view applications, test cases and run results — no changes.',
  },
]

export function InviteTeammateModal({ onClose }: { onClose: () => void }) {
  useEscapeToClose(onClose)
  const [email, setEmail] = useState('')
  const [role, setRole] = useState<Role>('member')
  const [error, setError] = useState<string | null>(null)
  const [sent, setSent] = useState(false)
  const [submitting, setSubmitting] = useState(false)

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault()
    setError(null)
    setSubmitting(true)
    try {
      await api.sendInvite({ email, role })
      setSent(true)
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'Could not send invite.')
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <div onClick={onClose} style={{ ...modalOverlay, zIndex: 90 }}>
      <form
        onClick={(e) => e.stopPropagation()}
        onSubmit={handleSubmit}
        style={{ ...modalPanel, maxWidth: 520 }}
      >
        <div style={modalHeader}>
          <div>
            <h2 style={modalTitle}>Invite member</h2>
            <p className="caption" style={{ margin: '4px 0 0', fontSize: 13 }}>
              They get an email invitation to the workspace. Access applies to every onboarded application.
            </p>
          </div>
          {!sent && (
            <button type="button" aria-label="Close" onClick={onClose} style={modalCloseButton}>
              <FontAwesomeIcon icon={faXmark} />
            </button>
          )}
        </div>

        {sent ? (
          <>
            <div style={{ padding: '4px 28px 22px' }}>
              <p style={{ fontSize: 13.5, color: 'var(--fg-3)', margin: 0 }}>Invite sent to {email}.</p>
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
                  <div style={{ display: 'flex', alignItems: 'baseline', gap: 8 }}>
                    <span style={{ fontSize: 10.5, fontWeight: 600, letterSpacing: '0.07em', textTransform: 'uppercase', color: 'var(--fg-4)' }}>Email address</span>
                    <span style={{ flex: 1 }} />
                    <span style={{ fontSize: 11, color: 'var(--fg-5)', whiteSpace: 'nowrap', flex: 'none' }}>Comma-separate for several</span>
                  </div>
                  <div
                    className="field-shell"
                    style={{
                      display: 'flex',
                      alignItems: 'center',
                      gap: 10,
                      height: 42,
                      padding: '0 13px',
                      borderRadius: 10,
                      border: '1px solid var(--border-2)',
                      background: 'var(--panel)',
                      boxShadow: 'inset 0 1px 2px rgba(16,20,30,0.04)',
                    }}
                  >
                    <input
                      type="email"
                      required
                      autoFocus
                      data-bare
                      placeholder="Enter their email"
                      value={email}
                      onChange={(e) => setEmail(e.target.value)}
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
                </div>

                <div style={{ display: 'flex', flexDirection: 'column', gap: 9 }}>
                  <span style={{ fontSize: 10.5, fontWeight: 600, letterSpacing: '0.07em', textTransform: 'uppercase', color: 'var(--fg-4)' }}>Role</span>
                  <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
                    {ROLE_OPTIONS.map((r) => {
                      const active = role === r.key
                      return (
                        <div
                          key={r.key}
                          onClick={() => setRole(r.key)}
                          style={{
                            display: 'flex',
                            alignItems: 'flex-start',
                            gap: 11,
                            padding: '11px 13px',
                            borderRadius: 10,
                            border: active ? '1px solid rgba(30,150,138,0.4)' : '1px solid var(--border-2)',
                            background: active ? 'rgba(30,150,138,0.08)' : 'var(--panel)',
                            cursor: 'pointer',
                          }}
                        >
                          <div
                            style={{
                              width: 16,
                              height: 16,
                              flex: 'none',
                              marginTop: 2,
                              borderRadius: 1000,
                              border: active ? '5px solid var(--accent-2)' : '1px solid var(--border-2)',
                              background: 'var(--panel)',
                              boxSizing: 'border-box',
                            }}
                          />
                          <div style={{ flex: 1, minWidth: 0 }}>
                            <div style={{ fontSize: 13.5, fontWeight: 600, color: 'var(--fg-1)' }}>{r.label}</div>
                            <div style={{ fontSize: 12, color: 'var(--fg-4)', marginTop: 3, lineHeight: '17px' }}>{r.hint}</div>
                          </div>
                        </div>
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

            <div style={{ ...modalFooter, justifyContent: 'space-between' }}>
              <span className="caption" style={{ fontSize: 12.5 }}>
                Invitation expires in 7 days
              </span>
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
    </div>
  )
}
