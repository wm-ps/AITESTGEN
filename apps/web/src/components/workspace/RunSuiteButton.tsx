import { useState } from 'react'
import { FontAwesomeIcon } from '@fortawesome/react-fontawesome'
import { faLayerGroup, faListCheck, faPlay, faXmark, type IconDefinition } from '@fortawesome/free-solid-svg-icons'
import { LoadingDots } from '../LoadingDots'
import { EnvironmentSelect } from '../environments/EnvironmentSelect'
import { DEFAULT_TARGET, viewportError, type RunTarget } from '../../runTarget'
import { TargetSelect } from './TargetSelect'
import { useEscapeToClose } from '../../hooks/useEscapeToClose'
import { modalButton, modalCloseButton, modalFooter, modalHeader, modalOverlay, modalPanel, modalTitle } from '../modalStyles'

type RunMode = 'full' | 'selective' | 'suites'

const RUN_MODES: { key: RunMode; title: string; body: string; action: string; icon: IconDefinition }[] = [
  { key: 'full', title: 'All test cases', body: 'Run every test case in this application.', action: 'Run all test cases', icon: faPlay },
  { key: 'selective', title: 'Selective run', body: 'Choose specific journeys or test cases.', action: 'Choose tests…', icon: faListCheck },
  { key: 'suites', title: 'Test suites', body: 'Run a saved group such as Smoke or Regression.', action: 'Choose suite…', icon: faLayerGroup },
]

const sectionHeading = { margin: 0, fontSize: 11, fontWeight: 700, letterSpacing: '0.06em', textTransform: 'uppercase', color: 'var(--fg-3)' } as const

// Run Suite Flow: clicking "Run" opens a modal dialog offering Full suite,
// Selective run or a saved Test suite — same overlay + card-panel modal shape as
// RunJourneysDialog.tsx/ScheduleDialog.tsx, replacing the earlier
// button-anchored dropdown menu with an actual dialog per the prototype.
export function RunSuiteButton({
  running,
  open,
  onOpenChange,
  environmentId,
  onEnvironmentChange,
  target,
  onTargetChange,
  onFullSuite,
  onOpenJourneysDialog,
  onOpenSuitesDialog,
}: {
  running: boolean
  // The dialog's state lives in the parent so the Selective run / Test suites
  // dialogs can send the user Back here with their choices intact. `null`
  // environment is the application's own (default) one.
  open: boolean
  onOpenChange: (open: boolean) => void
  environmentId: string | null
  onEnvironmentChange: (environmentId: string | null) => void
  target: RunTarget
  onTargetChange: (target: RunTarget) => void
  onFullSuite: () => void
  onOpenJourneysDialog: () => void
  onOpenSuitesDialog: () => void
}) {
  const setOpen = onOpenChange
  const sizeError = viewportError(target.viewport)
  const [mode, setMode] = useState<RunMode>('full')
  const selected = RUN_MODES.find((m) => m.key === mode) ?? RUN_MODES[0]
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
          // Fresh every time the button opens it; Back from a sub-dialog doesn't come through here.
          onTargetChange(DEFAULT_TARGET)
          onEnvironmentChange(null)
          setMode('full')
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
        <div role="dialog" aria-modal="true" aria-label="Run tests" style={modalOverlay}>
          <div style={{ ...modalPanel, maxWidth: 760 }}>
            <div style={modalHeader}>
              <h2 style={modalTitle}>Run tests</h2>
              <button type="button" aria-label="Close" onClick={() => setOpen(false)} style={modalCloseButton}>
                <FontAwesomeIcon icon={faXmark} />
              </button>
            </div>
            <div style={{ flex: 1, minHeight: 0, overflowY: 'auto', display: 'flex', flexDirection: 'column', gap: 12, padding: '4px 28px 22px' }}>
              <h3 style={sectionHeading}>Choose tests to run</h3>
              <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', gap: 12 }}>
                {RUN_MODES.map((m) => (
                  <button
                    key={m.key}
                    type="button"
                    className="run-mode-card"
                    aria-pressed={m.key === mode}
                    onClick={() => setMode(m.key)}
                    style={{
                      display: 'flex',
                      flexDirection: 'column',
                      alignItems: 'center',
                      gap: 10,
                      padding: '18px 10px',
                      borderRadius: 12,
                      border: '1px solid var(--border-2)',
                      background: 'var(--panel)',
                      cursor: 'pointer',
                      fontFamily: 'inherit',
                      fontSize: 14,
                      fontWeight: 600,
                      color: 'var(--fg)',
                    }}
                  >
                    <FontAwesomeIcon icon={m.icon} style={{ fontSize: 18, color: m.key === mode ? 'var(--accent)' : 'var(--fg-2)' }} />
                    {m.title}
                  </button>
                ))}
              </div>
              <p style={{ margin: 0, fontSize: 13.5, color: 'var(--fg-3)' }}>{selected.body}</p>

              <h3 style={{ ...sectionHeading, marginTop: 8 }}>Run configuration</h3>
              <div style={{ padding: 20, borderRadius: 12, border: '1px solid var(--border-2)', background: 'var(--bg-2)' }}>
                <TargetSelect
                  rows
                  value={target}
                  onChange={onTargetChange}
                  sideBySide={<EnvironmentSelect row label="Environment" value={environmentId} onChange={onEnvironmentChange} />}
                />
              </div>
            </div>
            <div style={modalFooter}>
              <button type="button" className="button-secondary" onClick={() => setOpen(false)} style={modalButton}>
                Cancel
              </button>
              <button
                type="button"
                className="button-primary"
                disabled={sizeError !== null}
                onClick={() => {
                  setOpen(false)
                  if (mode === 'full') onFullSuite()
                  else if (mode === 'suites') onOpenSuitesDialog()
                  else onOpenJourneysDialog()
                }}
                style={modalButton}
              >
                {selected.action}
              </button>
            </div>
          </div>
        </div>
      )}
    </>
  )
}
