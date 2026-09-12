import { useState } from 'react'
import { LoadingDots } from '../LoadingDots'

function PlayIcon() {
  return (
    <svg width={12} height={12} viewBox="0 0 24 24" fill="currentColor" aria-hidden="true">
      <path d="M6 4.5v15l13-7.5z" />
    </svg>
  )
}

// Run Suite Flow: "Run Suite" now opens a popover (Full Suite / Run
// Journey(s)…) instead of triggering a full-scope run directly — same
// button-anchored-menu shape DiscoverJourneys.tsx's JourneyRowMenu already
// uses (local `open` state, fixed click-outside overlay + absolute menu).
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

  return (
    <div style={{ position: 'relative' }}>
      <button
        type="button"
        aria-disabled={running}
        aria-haspopup="menu"
        aria-expanded={open}
        onClick={() => {
          if (running) return
          setOpen((o) => !o)
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
          background: running ? 'var(--fg-4)' : 'var(--accent)',
          boxShadow: running ? 'none' : '0 4px 14px rgba(30,150,138,0.3)',
          cursor: running ? 'not-allowed' : 'pointer',
        }}
      >
        <PlayIcon />
        {running ? <LoadingDots label="Running" /> : 'Run Suite'}
      </button>
      {open && (
        <>
          <div style={{ position: 'fixed', inset: 0, zIndex: 49 }} onClick={() => setOpen(false)} />
          <div
            role="menu"
            style={{
              position: 'absolute',
              right: 0,
              top: 'calc(100% + 6px)',
              minWidth: 200,
              borderRadius: 10,
              background: 'var(--panel)',
              border: '1px solid var(--border-2)',
              boxShadow: 'var(--panel-shadow)',
              overflow: 'hidden',
              zIndex: 50,
            }}
          >
            <button
              type="button"
              role="menuitem"
              onClick={() => {
                setOpen(false)
                onFullSuite()
              }}
              style={{
                display: 'block',
                width: '100%',
                textAlign: 'left',
                padding: '10px 14px',
                background: 'none',
                border: 'none',
                fontSize: 13.5,
                color: 'var(--fg-1)',
                cursor: 'pointer',
                fontFamily: 'inherit',
              }}
            >
              Full Suite
            </button>
            <button
              type="button"
              role="menuitem"
              onClick={() => {
                setOpen(false)
                onOpenJourneysDialog()
              }}
              style={{
                display: 'block',
                width: '100%',
                textAlign: 'left',
                padding: '10px 14px',
                background: 'none',
                border: 'none',
                fontSize: 13.5,
                color: 'var(--fg-1)',
                cursor: 'pointer',
                fontFamily: 'inherit',
              }}
            >
              Selective Run…
            </button>
          </div>
        </>
      )}
    </div>
  )
}
