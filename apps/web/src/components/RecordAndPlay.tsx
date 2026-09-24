import { useEffect, useRef, useState } from 'react'
import { faArrowUpRightFromSquare, faCircleDot, faVideo } from '@fortawesome/free-solid-svg-icons'
import { FontAwesomeIcon } from '@fortawesome/react-fontawesome'
import { ApiError, api, type RecordingAuthMode } from '../api'
import { useRecordingControlSocket } from '../hooks/useRecordingControlSocket'
import { AppIdentityLine } from './AppIdentityLine'
import { LoadingDots } from './LoadingDots'
import { buildRecordingSessionWindowUrl } from './RecordingSessionWindow'

// Record and Play: a human drives a real headed Chromium the worker hosts,
// through the real `playwright codegen` CLI — never a custom action-capture
// reimplementation, never an LLM, and never an iframe of the application
// under test. The live session (Codegen's browser window plus its separate
// Inspector window, streamed over the classic noVNC stack — Xvfb + x11vnc)
// opens in its own real browser tab (`RecordingSessionWindow.tsx`) rather
// than embedded inline here — this tab only mints the session, opens that
// window, and tracks its own status/saved/failed off a second, independent
// `control` websocket connection (the recording service already broadcasts
// to every attached control socket, so this tab and the popped-out window
// each having their own is a supported shape, not a workaround).

type Stage = 'idle' | 'starting' | 'recording' | 'saving' | 'success' | 'error'

export function RecordAndPlay({
  applicationId,
  applicationName,
  applicationUrl,
  onSaved,
}: {
  applicationId: string
  applicationName: string
  applicationUrl: string
  onSaved: (message: string) => void
}) {
  const [authMode, setAuthMode] = useState<RecordingAuthMode>('logged_out')
  // 'idle'/'starting'/'error' here only ever describe the pre-mint phase —
  // once a session is minted, `stage` below hands off entirely to the
  // control-socket hook's own stage (recording/saving/success/error).
  const [preConnectPhase, setPreConnectPhase] = useState<'idle' | 'starting'>('idle')
  const [mintError, setMintError] = useState<string | null>(null)
  const [controlWsUrl, setControlWsUrl] = useState<string | null>(null)

  const popupUrlRef = useRef<string | null>(null)
  const popupWindowRef = useRef<Window | null>(null)
  const [popupBlocked, setPopupBlocked] = useState(false)

  const { stage: socketStage, reconnecting, errorMessage: socketError, saved, stopWarning, sendStop } =
    useRecordingControlSocket(controlWsUrl)

  const stage: Stage = mintError ? 'error' : controlWsUrl ? socketStage : preConnectPhase
  const errorMessage = mintError ?? socketError

  const startRecording = async () => {
    setPreConnectPhase('starting')
    setMintError(null)
    try {
      const session = await api.createRecordingSession(applicationId, authMode)
      const popupUrl = buildRecordingSessionWindowUrl({
        vncWsUrl: session.vnc_ws_url,
        controlWsUrl: session.control_ws_url,
        authMode,
        applicationName,
      })
      popupUrlRef.current = popupUrl
      const popup = window.open(popupUrl, '_blank', 'noopener')
      popupWindowRef.current = popup
      setPopupBlocked(popup === null)
      setControlWsUrl(session.control_ws_url)
    } catch (err) {
      setMintError(err instanceof ApiError ? err.message : 'Could not start a recording session.')
      setPreConnectPhase('idle')
    }
  }

  const reopenPopup = () => {
    if (popupWindowRef.current && !popupWindowRef.current.closed) {
      popupWindowRef.current.focus()
      return
    }
    if (!popupUrlRef.current) return
    const popup = window.open(popupUrlRef.current, '_blank', 'noopener')
    popupWindowRef.current = popup
    setPopupBlocked(popup === null)
  }

  const resetToIdle = () => {
    setControlWsUrl(null)
    popupUrlRef.current = null
    popupWindowRef.current = null
    setPopupBlocked(false)
    setMintError(null)
    setPreConnectPhase('idle')
  }

  // The popup shows its own "Recording saved" confirmation and closes
  // itself — this tab doesn't wait around for that, it hands off a toast
  // and goes straight back to idle, ready to record again immediately.
  useEffect(() => {
    if (stage !== 'success' || !saved) return
    onSaved(`Test case TC-${String(saved.testCaseNumber).padStart(3, '0')} was added to the test suite.`)
    resetToIdle()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [stage, saved])

  return (
    <div style={{ maxWidth: 1560, margin: '0 auto', width: '100%', display: 'flex', flexDirection: 'column', gap: 20 }}>
      <div style={{ display: 'flex', flexDirection: 'column', gap: 4 }}>
        <h1 style={{ fontSize: 20, lineHeight: '26px', color: 'var(--fg)', letterSpacing: '-0.02em', fontWeight: 600, margin: 0 }}>
          Record and play
        </h1>
        <AppIdentityLine name={applicationName} url={applicationUrl} />
        <div style={{ fontSize: 13.5, color: 'var(--fg-3)', marginTop: 4, maxWidth: 620 }}>
          Walk through a flow in a real browser once. Vantage turns the session into a maintained Playwright test that
          lives alongside the generated suite — same locators, same fixtures, same self-healing.
        </div>
      </div>

      <div
        style={{
          background: 'linear-gradient(180deg,rgba(255,255,255,0.92),rgba(255,255,255,0.74))',
          backdropFilter: 'blur(16px) saturate(1.25)',
          border: '1px solid var(--border-1)',
          borderRadius: 14,
          boxShadow: 'var(--panel-shadow)',
          display: 'flex',
          flexDirection: 'column',
          alignItems: 'center',
          justifyContent: 'center',
          padding: '56px 24px',
          minHeight: 420,
          gap: 20,
        }}
      >
        {(stage === 'idle' || stage === 'starting') && (
          <IdleState authMode={authMode} onAuthModeChange={setAuthMode} starting={stage === 'starting'} onStart={startRecording} />
        )}

        {(stage === 'recording' || stage === 'saving') && (
          <AwaitingPopupState
            popupUrl={popupUrlRef.current}
            popupBlocked={popupBlocked}
            saving={stage === 'saving'}
            reconnecting={reconnecting}
            stopWarning={stopWarning}
            onReopen={reopenPopup}
            onStop={sendStop}
          />
        )}

        {stage === 'error' && <ErrorState errorMessage={errorMessage} onTryAgain={resetToIdle} />}
      </div>
    </div>
  )
}

function IdleState({
  authMode,
  onAuthModeChange,
  starting,
  onStart,
}: {
  authMode: RecordingAuthMode
  onAuthModeChange: (mode: RecordingAuthMode) => void
  starting: boolean
  onStart: () => void
}) {
  return (
    <>
      <RecordingsIllustration />
      <div role="radiogroup" aria-label="Recording mode" style={{ display: 'flex', gap: 10 }}>
        <AuthModeOption
          mode="logged_out"
          selected={authMode === 'logged_out'}
          onSelect={onAuthModeChange}
          title="Record a login flow"
          description="Start from a logged-out browser — your login steps become part of the test."
        />
        <AuthModeOption
          mode="authenticated"
          selected={authMode === 'authenticated'}
          onSelect={onAuthModeChange}
          title="Record an authenticated flow"
          description="Start already signed in, using this application's stored credentials."
        />
      </div>
      <button
        type="button"
        onClick={onStart}
        disabled={starting}
        style={{
          display: 'inline-flex',
          alignItems: 'center',
          gap: 8,
          height: 38,
          padding: '0 20px',
          borderRadius: 8,
          background: 'var(--accent)',
          color: 'white',
          border: 'none',
          fontSize: 13.5,
          fontWeight: 600,
          cursor: starting ? 'default' : 'pointer',
          opacity: starting ? 0.7 : 1,
        }}
      >
        {starting ? (
          <LoadingDots label="Starting" />
        ) : (
          <>
            <FontAwesomeIcon icon={faVideo} style={{ fontSize: 12 }} />
            Record a flow
          </>
        )}
      </button>
    </>
  )
}

function AuthModeOption({
  mode,
  selected,
  onSelect,
  title,
  description,
}: {
  mode: RecordingAuthMode
  selected: boolean
  onSelect: (mode: RecordingAuthMode) => void
  title: string
  description: string
}) {
  return (
    <button
      type="button"
      role="radio"
      aria-checked={selected}
      onClick={() => onSelect(mode)}
      style={{
        width: 240,
        textAlign: 'left',
        padding: '12px 14px',
        borderRadius: 10,
        border: selected ? '1px solid var(--accent)' : '1px solid var(--border-2)',
        background: selected ? 'var(--accent-wash)' : 'var(--panel)',
        cursor: 'pointer',
        display: 'flex',
        alignItems: 'flex-start',
        gap: 10,
      }}
    >
      <span
        aria-hidden="true"
        style={{
          flex: 'none',
          marginTop: 2,
          width: 16,
          height: 16,
          borderRadius: '50%',
          border: `1.5px solid ${selected ? 'var(--accent)' : 'var(--border-3)'}`,
          background: 'var(--panel)',
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
        }}
      >
        {selected && <span style={{ width: 8, height: 8, borderRadius: '50%', background: 'var(--accent)' }} />}
      </span>
      <span style={{ display: 'flex', flexDirection: 'column', gap: 4 }}>
        <span style={{ fontSize: 13, fontWeight: 600, color: selected ? 'var(--accent)' : 'var(--fg-2)' }}>{title}</span>
        <span style={{ fontSize: 12, color: 'var(--fg-3)', lineHeight: 1.4 }}>{description}</span>
      </span>
    </button>
  )
}

// Shown in the main tab while the live session runs in its own popped-out
// window (RecordingSessionWindow.tsx) — no video here, just status plus a
// way back into that window and a "Stop and Save" fallback in case the
// popup got closed without stopping (the recording service accepts a stop
// from either tab's own control socket indifferently).
function AwaitingPopupState({
  popupUrl,
  popupBlocked,
  saving,
  reconnecting,
  stopWarning,
  onReopen,
  onStop,
}: {
  popupUrl: string | null
  popupBlocked: boolean
  saving: boolean
  reconnecting: boolean
  stopWarning: string | null
  onReopen: () => void
  onStop: () => void
}) {
  return (
    <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 16, textAlign: 'center', maxWidth: 420 }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
        <FontAwesomeIcon icon={faCircleDot} style={{ fontSize: 12, color: 'var(--bad)' }} />
        <span style={{ fontSize: 14, fontWeight: 600, color: 'var(--fg-2)' }}>
          {saving ? 'Saving your recording' : 'Recording in progress'}
        </span>
      </div>
      <div style={{ fontSize: 13, color: 'var(--fg-3)', lineHeight: 1.5 }}>
        {saving
          ? 'Finishing up in the recording window — this only takes a moment.'
          : 'Perform your flow in the recording window that just opened. Come back here once you’re done, or use Stop and Save below.'}
      </div>
      {reconnecting && (
        <span style={{ fontSize: 12, color: 'var(--fg-3)' }}>
          <LoadingDots label="Reconnecting" />
        </span>
      )}
      {popupBlocked && popupUrl && (
        <a
          href={popupUrl}
          target="_blank"
          rel="noopener"
          style={{ fontSize: 12.5, color: 'var(--accent)', textDecoration: 'underline' }}
        >
          Your browser blocked the pop-up — click here to open the recording window
        </a>
      )}
      {stopWarning && <div style={{ fontSize: 12.5, color: 'var(--warn-strong, #a15c00)' }}>{stopWarning}</div>}
      <div style={{ display: 'flex', gap: 10 }}>
        <button
          type="button"
          onClick={onReopen}
          style={{
            display: 'inline-flex',
            alignItems: 'center',
            gap: 8,
            height: 34,
            padding: '0 16px',
            borderRadius: 8,
            border: '1px solid var(--border-2)',
            background: 'var(--panel)',
            fontSize: 13,
            fontWeight: 500,
            color: 'var(--fg-2)',
            cursor: 'pointer',
          }}
        >
          <FontAwesomeIcon icon={faArrowUpRightFromSquare} style={{ fontSize: 11 }} />
          Reopen recording window
        </button>
        <button
          type="button"
          onClick={onStop}
          disabled={saving}
          style={{
            height: 34,
            padding: '0 16px',
            borderRadius: 8,
            background: 'var(--bad)',
            color: 'white',
            border: 'none',
            fontSize: 13,
            fontWeight: 600,
            cursor: saving ? 'default' : 'pointer',
            opacity: saving ? 0.7 : 1,
          }}
        >
          {saving ? <LoadingDots label="Saving" /> : 'Stop and Save'}
        </button>
      </div>
    </div>
  )
}

function ErrorState({ errorMessage, onTryAgain }: { errorMessage: string | null; onTryAgain: () => void }) {
  return (
    <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 14, textAlign: 'center', maxWidth: 480 }}>
      <div style={{ fontSize: 15, fontWeight: 600, color: 'var(--bad)' }}>The recording could not be saved</div>
      {errorMessage && (
        <div
          style={{
            fontSize: 12.5,
            color: 'var(--fg-3)',
            fontFamily: 'var(--font-mono)',
            whiteSpace: 'pre-wrap',
            background: 'var(--panel-2)',
            border: '1px solid var(--border-2)',
            borderRadius: 8,
            padding: '10px 12px',
            maxHeight: 160,
            overflow: 'auto',
          }}
        >
          {errorMessage}
        </div>
      )}
      <button
        type="button"
        onClick={onTryAgain}
        style={{ height: 36, padding: '0 18px', borderRadius: 8, background: 'var(--accent)', color: 'white', border: 'none', fontSize: 13, fontWeight: 600, cursor: 'pointer' }}
      >
        Try again
      </button>
    </div>
  )
}

// Matches the prototype's own illustration exactly: a scrubber bar with a
// playhead partway through, two overlapping video-frame cards behind it,
// and a recording-dot badge — the one illustration this screen doesn't
// share with EmptyState.tsx's family, since nothing else in the app is a
// video/session recording.
function RecordingsIllustration() {
  return (
    <div style={{ position: 'relative', width: 196, height: 120, marginBottom: 4 }}>
      <div style={{ position: 'absolute', left: '50%', top: '50%', transform: 'translate(-50%,-50%)', width: 220, height: 220, borderRadius: 1000, background: 'var(--glow)' }} />
      <div style={{ position: 'absolute', left: 16, top: 8, width: 74, height: 52, borderRadius: 9, background: 'var(--panel-2)', border: '1px solid var(--border-2)' }} />
      <div style={{ position: 'absolute', left: 60, top: 22, width: 74, height: 52, borderRadius: 9, background: 'var(--panel-2)', border: '1px solid var(--border-3)', boxShadow: '0 12px 26px rgba(0,0,0,0.22)' }} />
      <div style={{ position: 'absolute', right: 8, top: 0, width: 46, height: 46, borderRadius: 1000, background: 'rgba(245,86,107,0.12)', border: '1px solid rgba(245,86,107,0.3)', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
        <span style={{ width: 13, height: 13, borderRadius: 1000, background: 'var(--bad)' }} />
      </div>
      <div style={{ position: 'absolute', left: 0, right: 0, bottom: 26, height: 8, borderRadius: 1000, background: 'var(--panel-2)', border: '1px solid var(--border-2)', overflow: 'hidden', display: 'flex' }}>
        <div style={{ width: '34%', height: '100%', background: 'var(--accent)', opacity: 0.55 }} />
      </div>
      <div style={{ position: 'absolute', left: 'calc(34% - 7px)', bottom: 19, width: 14, height: 22, borderRadius: 4, background: 'var(--accent)', boxShadow: '0 4px 14px rgba(30,150,138,0.4)' }} />
    </div>
  )
}
