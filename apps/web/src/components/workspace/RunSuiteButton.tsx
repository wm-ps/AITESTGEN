import { useState } from 'react'
import { FontAwesomeIcon } from '@fortawesome/react-fontawesome'
import { faChevronRight, faListCheck, faPlay } from '@fortawesome/free-solid-svg-icons'
import { Spinner } from '../LoadingDots'
import { useEscapeToClose } from '../../hooks/useEscapeToClose'

const RUN_MODES: { key: 'full' | 'selective'; icon: typeof faPlay; title: string; body: string }[] = [
  { key: 'full', icon: faPlay, title: 'Full suite', body: 'Run every test case in this application.' },
  { key: 'selective', icon: faListCheck, title: 'Selective run', body: 'Choose specific journeys or test cases to run.' },
]

// Run Suite Flow: clicking "Run" opens a modal dialog offering Full suite or
// Selective run — same overlay + card-panel modal shape as
// RunJourneysDialog.tsx/ScheduleDialog.tsx, replacing the earlier
// button-anchored dropdown menu with an actual dialog per the prototype.
export function RunSuiteButton({
  running,
  onFullSuite,
  onOpenJourneysDialog,
}: {
  running: boolean
  onFullSuite: () => void
  onOpenJourneysDialog: () => void
}) {
  const [open, setOpen] = useState(false)
  useEscapeToClose(() => setOpen(false), open)

  return (
    <>
      <button
        type="button"
        aria-disabled={running}
        aria-haspopup="dialog"
        aria-expanded={open}
        onClick={() => {
          if (running) return
          setOpen(true)
        }}
        style={{
          display: 'inline-flex',
          alignItems: 'center',
          gap: 8,
          height: 36,
          padding: '0 18px',
          borderRadius: 8,
          border: 'none',
          fontSize: 13.5,
          fontWeight: 600,
          flex: 'none',
          whiteSpace: 'nowrap',
          color: '#fff',
          background: 'var(--accent)',
          opacity: running ? 0.65 : 1,
          boxShadow: running ? 'none' : '0 4px 14px rgba(30,150,138,0.3)',
          cursor: running ? 'not-allowed' : 'pointer',
        }}
      >
        {running ? <Spinner size={12} /> : <FontAwesomeIcon icon={faPlay} style={{ fontSize: 11 }} />}
        {running ? 'Running…' : 'Run'}
      </button>

      {open && (
        <div
          role="dialog"
          aria-modal="true"
          aria-label="Run tests"
          onClick={() => setOpen(false)}
          style={{
            position: 'fixed',
            inset: 0,
            background: 'rgba(15,23,42,0.35)',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            zIndex: 50,
          }}
        >
          <div
            onClick={(e) => e.stopPropagation()}
            style={{
              background: 'linear-gradient(180deg,rgba(255,255,255,0.96),rgba(255,255,255,0.82))',
              backdropFilter: 'blur(20px) saturate(1.3)',
              border: '1px solid var(--border-2)',
              borderRadius: 16,
              boxShadow: '0 30px 80px rgba(8,12,20,0.34), var(--panel-shadow)',
              width: '100%',
              maxWidth: 440,
              padding: '24px 24px 18px',
              boxSizing: 'border-box',
            }}
          >
            <h2 style={{ fontSize: 17, fontWeight: 600, color: 'var(--fg)', margin: '0 0 16px' }}>Run tests</h2>
            <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
              {RUN_MODES.map((mode) => (
                <button
                  key={mode.key}
                  type="button"
                  onClick={() => {
                    setOpen(false)
                    if (mode.key === 'full') onFullSuite()
                    else onOpenJourneysDialog()
                  }}
                  style={{
                    display: 'flex',
                    alignItems: 'center',
                    gap: 12,
                    width: '100%',
                    padding: '12px 14px',
                    borderRadius: 10,
                    border: '1px solid var(--border-2)',
                    background: 'var(--panel)',
                    cursor: 'pointer',
                    textAlign: 'left',
                    fontFamily: 'inherit',
                  }}
                >
                  <span
                    style={{
                      width: 32,
                      height: 32,
                      flex: 'none',
                      borderRadius: 8,
                      background: 'var(--chip)',
                      display: 'flex',
                      alignItems: 'center',
                      justifyContent: 'center',
                      color: 'var(--accent-2)',
                    }}
                  >
                    <FontAwesomeIcon icon={mode.icon} style={{ fontSize: 13 }} />
                  </span>
                  <span style={{ flex: 1, minWidth: 0 }}>
                    <span style={{ display: 'block', fontSize: 13.5, fontWeight: 600, color: 'var(--fg)' }}>{mode.title}</span>
                    <span style={{ display: 'block', fontSize: 12.5, color: 'var(--fg-3)', marginTop: 2 }}>{mode.body}</span>
                  </span>
                  <FontAwesomeIcon icon={faChevronRight} style={{ fontSize: 11, color: 'var(--fg-4)' }} />
                </button>
              ))}
            </div>
            <div style={{ display: 'flex', justifyContent: 'flex-end', marginTop: 18 }}>
              <button type="button" className="button-secondary" onClick={() => setOpen(false)} style={{ padding: '9px 16px', fontSize: 13.5 }}>
                Cancel
              </button>
            </div>
          </div>
        </div>
      )}
    </>
  )
}
