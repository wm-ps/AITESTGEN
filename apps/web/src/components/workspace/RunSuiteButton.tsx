import { useState } from 'react'
import { FontAwesomeIcon } from '@fortawesome/react-fontawesome'
import { faPlay, faXmark } from '@fortawesome/free-solid-svg-icons'
import { LoadingDots } from '../LoadingDots'
import { EnvironmentSelect } from '../environments/EnvironmentSelect'
import { DEFAULT_TARGET, viewportError, type RunTarget } from '../../runTarget'
import { TargetSelect } from './TargetSelect'
import { useEscapeToClose } from '../../hooks/useEscapeToClose'
import { modalButton, modalCloseButton, modalFooter, modalHeader, modalOverlay, modalPanel, modalTitle } from '../modalStyles'

const RUN_MODES: { key: 'full' | 'selective' | 'suites'; title: string; body: string }[] = [
  { key: 'full', title: 'All test cases', body: 'Run every test case in this application.' },
  { key: 'selective', title: 'Selective run', body: 'Choose specific journeys or test cases to run.' },
  { key: 'suites', title: 'Test suites', body: 'Run a saved group of test cases, like Smoke or Regression.' },
]

// Run Suite Flow: clicking "Run" opens a modal dialog offering Full suite,
// Selective run or a saved Test suite — same overlay + card-panel modal shape as
// RunJourneysDialog.tsx/ScheduleDialog.tsx, replacing the earlier
// button-anchored dropdown menu with an actual dialog per the prototype.
export function RunSuiteButton({
  running,
  onFullSuite,
  onOpenJourneysDialog,
  onOpenSuitesDialog,
}: {
  running: boolean
  // All get the environment picked in the dialog — null is the application's
  // own (default) one — and the browsers and window size to run on.
  onFullSuite: (environmentId: string | null, target: RunTarget) => void
  onOpenJourneysDialog: (environmentId: string | null, target: RunTarget) => void
  onOpenSuitesDialog: (environmentId: string | null, target: RunTarget) => void
}) {
  const [open, setOpen] = useState(false)
  const [environmentId, setEnvironmentId] = useState<string | null>(null)
  // Chrome at 1280 × 720 every time the dialog opens; the last choice isn't kept.
  const [target, setTarget] = useState<RunTarget>(DEFAULT_TARGET)
  const sizeError = viewportError(target.viewport)
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
          setTarget(DEFAULT_TARGET)
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
        {running ? <LoadingDots label="Running" /> : <><FontAwesomeIcon icon={faPlay} style={{ fontSize: 11 }} />Run</>}
      </button>

      {open && (
        <div role="dialog" aria-modal="true" aria-label="Run tests" onClick={() => setOpen(false)} style={modalOverlay}>
          <div onClick={(e) => e.stopPropagation()} style={{ ...modalPanel, maxWidth: 440 }}>
            <div style={modalHeader}>
              <h2 style={modalTitle}>Run tests</h2>
              <button type="button" aria-label="Close" onClick={() => setOpen(false)} style={modalCloseButton}>
                <FontAwesomeIcon icon={faXmark} />
              </button>
            </div>
            <div style={{ flex: 1, minHeight: 0, overflowY: 'auto', display: 'flex', flexDirection: 'column', gap: 14, padding: '4px 28px 22px' }}>
              <EnvironmentSelect label="Run on environment" value={environmentId} onChange={setEnvironmentId} />
              <TargetSelect value={target} onChange={setTarget} />
              <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
              {RUN_MODES.map((mode) => (
                <button
                  key={mode.key}
                  type="button"
                  disabled={sizeError !== null}
                  onClick={() => {
                    setOpen(false)
                    if (mode.key === 'full') onFullSuite(environmentId, target)
                    else if (mode.key === 'suites') onOpenSuitesDialog(environmentId, target)
                    else onOpenJourneysDialog(environmentId, target)
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
                    cursor: sizeError ? 'not-allowed' : 'pointer',
                    opacity: sizeError ? 0.6 : 1,
                    textAlign: 'left',
                    fontFamily: 'inherit',
                  }}
                >
                  <span style={{ flex: 1, minWidth: 0 }}>
                    <span style={{ display: 'block', fontSize: 13.5, fontWeight: 600, color: 'var(--fg)' }}>{mode.title}</span>
                    <span style={{ display: 'block', fontSize: 12.5, color: 'var(--fg-3)', marginTop: 2 }}>{mode.body}</span>
                  </span>
                </button>
              ))}
            </div>
            </div>
            <div style={modalFooter}>
              <button type="button" className="button-secondary" onClick={() => setOpen(false)} style={modalButton}>
                Cancel
              </button>
            </div>
          </div>
        </div>
      )}
    </>
  )
}
