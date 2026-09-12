import { useState } from 'react'
import { FontAwesomeIcon } from '@fortawesome/react-fontawesome'
import { faEnvelope, faPaperPlane, faXmark } from '@fortawesome/free-solid-svg-icons'
import { ApiError, api } from '../api'
import { LoadingDots } from './LoadingDots'
import { useEscapeToClose } from '../hooks/useEscapeToClose'

const ROLES = [
  {
    key: 'member' as const,
    label: 'Member',
    hint: 'Can onboard applications, review scenarios and trigger runs.',
  },
  {
    key: 'admin' as const,
    label: 'Admin',
    hint: 'Everything a member can do, plus saved credentials and discovery limits.',
  },
]

export function InviteTeammateModal({ onClose }: { onClose: () => void }) {
  useEscapeToClose(onClose)
  const [email, setEmail] = useState('')
  const [role, setRole] = useState<'admin' | 'member'>('member')
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
      <form
        onClick={(e) => e.stopPropagation()}
        onSubmit={handleSubmit}
        style={{
          width: '100%',
          maxWidth: 520,
          position: 'relative',
          overflow: 'hidden',
          background: 'linear-gradient(180deg,rgba(255,255,255,0.96),rgba(255,255,255,0.82))',
          backdropFilter: 'blur(20px) saturate(1.3)',
          border: '1px solid var(--border-2)',
          borderRadius: 16,
          boxShadow: '0 30px 80px rgba(8,12,20,0.34), var(--panel-shadow)',
          maxHeight: 'calc(100vh - 48px)',
          overflowY: 'auto',
          boxSizing: 'border-box',
        }}
      >
        <div
          aria-hidden="true"
          style={{ position: 'absolute', left: -60, top: -120, width: 320, height: 320, borderRadius: 1000, background: 'var(--glow)', pointerEvents: 'none' }}
        />

        <div style={{ position: 'relative', display: 'flex', alignItems: 'flex-start', gap: 13, padding: '22px 22px 18px', borderBottom: '1px solid var(--line)' }}>
          <div
            style={{
              width: 38,
              height: 38,
              flex: 'none',
              borderRadius: 11,
              background: 'linear-gradient(160deg,var(--accent),var(--accent-deep))',
              color: '#fff',
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
              boxShadow: 'var(--accent-glow)',
            }}
          >
            <FontAwesomeIcon icon={faPaperPlane} style={{ fontSize: 15 }} />
          </div>
          <div style={{ flex: 1, minWidth: 0 }}>
            <h2 style={{ fontSize: 16, fontWeight: 600, color: 'var(--fg)', letterSpacing: '-0.015em', margin: 0 }}>Invite member</h2>
            <div style={{ fontSize: 12.5, color: 'var(--fg-3)', marginTop: 3 }}>
              They get an email invitation to the workspace. Access applies to every onboarded application.
            </div>
          </div>
          {!sent && (
            <button
              type="button"
              onClick={onClose}
              aria-label="Close"
              style={{ width: 28, height: 28, flex: 'none', borderRadius: 8, display: 'flex', alignItems: 'center', justifyContent: 'center', color: 'var(--fg-4)', cursor: 'pointer', background: 'none', border: 'none' }}
            >
              <FontAwesomeIcon icon={faXmark} style={{ fontSize: 13 }} />
            </button>
          )}
        </div>

        {sent ? (
          <div style={{ position: 'relative', padding: '20px 22px 22px', display: 'flex', flexDirection: 'column', gap: 14 }}>
            <p style={{ fontSize: 13.5, color: 'var(--fg-3)', margin: 0 }}>Invite sent to {email}.</p>
            <button
              type="button"
              onClick={onClose}
              style={{ alignSelf: 'flex-end', display: 'inline-flex', alignItems: 'center', height: 36, padding: '0 18px', borderRadius: 9, background: 'var(--accent)', color: '#fff', fontSize: 13, fontWeight: 600, cursor: 'pointer', boxShadow: 'var(--accent-glow)', border: 'none' }}
            >
              Done
            </button>
          </div>
        ) : (
          <>
            <fieldset disabled={submitting} style={{ border: 0, margin: 0, padding: 0, display: 'contents' }}>
              <div style={{ position: 'relative', display: 'flex', flexDirection: 'column', gap: 18, padding: '20px 22px 22px' }}>
                <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
                  <div style={{ display: 'flex', alignItems: 'baseline', gap: 8 }}>
                    <span style={{ fontSize: 10.5, fontWeight: 600, letterSpacing: '0.07em', textTransform: 'uppercase', color: 'var(--fg-4)' }}>Email address</span>
                    <span style={{ flex: 1 }} />
                    <span style={{ fontSize: 11, color: 'var(--fg-5)', whiteSpace: 'nowrap', flex: 'none' }}>Comma-separate for several</span>
                  </div>
                  <div
                    style={{
                      display: 'flex',
                      alignItems: 'center',
                      gap: 10,
                      height: 42,
                      padding: '0 13px',
                      borderRadius: 10,
                      border: '1px solid var(--border-2)',
                      background: 'var(--bg-2)',
                      boxShadow: 'inset 0 1px 2px rgba(16,20,30,0.04)',
                    }}
                  >
                    <FontAwesomeIcon icon={faEnvelope} style={{ fontSize: 13, color: 'var(--fg-5)', flexShrink: 0 }} />
                    <input
                      type="email"
                      required
                      autoFocus
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
                    {ROLES.map((r) => {
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

            <div style={{ position: 'relative', display: 'flex', alignItems: 'center', gap: 10, padding: '14px 22px', borderTop: '1px solid var(--line)', background: 'var(--panel-2)' }}>
              <div style={{ flex: 1, minWidth: 0, fontSize: 11.5, color: 'var(--fg-5)', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                Invitation expires in 7 days
              </div>
              <button
                type="button"
                onClick={onClose}
                style={{ display: 'inline-flex', alignItems: 'center', height: 36, padding: '0 16px', borderRadius: 9, border: '1px solid var(--border-2)', background: 'var(--panel)', color: 'var(--fg-2)', fontSize: 13, fontWeight: 500, cursor: 'pointer', whiteSpace: 'nowrap', flex: 'none' }}
              >
                Cancel
              </button>
              <button
                type="submit"
                disabled={submitting}
                style={{
                  display: 'inline-flex',
                  alignItems: 'center',
                  gap: 8,
                  height: 36,
                  padding: '0 18px',
                  borderRadius: 9,
                  background: 'var(--accent)',
                  color: '#fff',
                  fontSize: 13,
                  fontWeight: 600,
                  cursor: submitting ? 'default' : 'pointer',
                  opacity: submitting ? 0.75 : 1,
                  boxShadow: 'var(--accent-glow)',
                  whiteSpace: 'nowrap',
                  flex: 'none',
                  border: 'none',
                }}
              >
                {submitting ? (
                  <LoadingDots label="Sending" />
                ) : (
                  <>
                    <FontAwesomeIcon icon={faPaperPlane} style={{ fontSize: 11 }} />
                    Send invite
                  </>
                )}
              </button>
            </div>
          </>
        )}
      </form>
    </div>
  )
}
