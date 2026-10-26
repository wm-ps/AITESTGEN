import { useCallback, useEffect, useRef, useState } from 'react'
import RFB from '@novnc/novnc'
import { faCircleDot, faTriangleExclamation } from '@fortawesome/free-solid-svg-icons'
import { FontAwesomeIcon } from '@fortawesome/react-fontawesome'
import type { RecordingAuthMode } from '../api'
import { useRecordingControlSocket } from '../hooks/useRecordingControlSocket'
import { LoadingDots } from './LoadingDots'

// The chrome-less page that opens in its own real browser tab when a
// recording starts (`RecordAndPlay.tsx`'s `startRecording` calls
// `window.open` on the URL `buildRecordingSessionWindowUrl` below builds) —
// this is the "regular playwright codegen browser flow" surface: a human
// drives a real headed Chromium the worker hosts, through the real
// `playwright codegen` CLI, streamed here over the classic noVNC stack
// (Xvfb + x11vnc). This window holds its own independent `control` and
// `vnc` websocket connections to the same RecordingSession the opener tab
// minted — the recording service tracks both as sets and broadcasts to
// every attached control socket, so this window and the opener each having
// their own connection is an already-supported shape (see
// `apps/workers/recording/src/recording_worker/runtime.py`), not a
// workaround.
//
// ponytail: talks to `@novnc/novnc`'s `RFB` class directly rather than the
// `react-vnc` wrapper — that package declares a `react-scripts` peer
// dependency that conflicts with this project's own TypeScript version.
// `RFB` itself is a small, dependency-free class (see `VncCanvas`'s own
// effect below for the whole integration surface this actually needs), so
// the direct-usage version costs little. Revisit `react-vnc` if its
// peer-dependency range is ever relaxed, or if this component's manual
// `RFB` lifecycle/event wiring grows past what `VncCanvas` covers today.

export type RecordingPopupParams = {
  vncWsUrl: string
  controlWsUrl: string
  authMode: RecordingAuthMode
  applicationName: string
}

export function buildRecordingSessionWindowUrl(params: RecordingPopupParams): string {
  const search = new URLSearchParams({
    vnc: params.vncWsUrl,
    control: params.controlWsUrl,
    auth: params.authMode,
    app: params.applicationName,
  })
  return `${window.location.origin}/recording-session?${search.toString()}`
}

export function getRecordingPopupParamsFromUrl(): RecordingPopupParams | null {
  if (window.location.pathname !== '/recording-session') return null
  const params = new URLSearchParams(window.location.search)
  const vncWsUrl = params.get('vnc')
  const controlWsUrl = params.get('control')
  if (!vncWsUrl || !controlWsUrl) return null
  return {
    vncWsUrl,
    controlWsUrl,
    authMode: params.get('auth') === 'authenticated' ? 'authenticated' : 'logged_out',
    applicationName: params.get('app') ?? '',
  }
}

// Long enough to actually read the result before the tab closes itself —
// only the success and cancelled paths auto-close; an error state stays open
// so the human can read why and decide what to do (retry, or close manually).
const AUTO_CLOSE_DELAY_MS = 2500

// The service replies to a cancel before any teardown, so a healthy cancel
// answers in well under a second — this is only a backstop.
const CANCEL_REPLY_TIMEOUT_MS = 20_000

export function RecordingSessionWindow({ vncWsUrl, controlWsUrl, authMode, applicationName }: RecordingPopupParams) {
  const { stage, reconnecting, errorMessage, saved, connected, stopWarning, sendStop, cancelError, sendCancel } =
    useRecordingControlSocket(controlWsUrl)
  const [confirmingCancel, setConfirmingCancel] = useState(false)
  // Waiting on the service's `cancelled` (or `cancel_failed`) — the stage
  // only ever flips to 'cancelled' once the cancel is actually persisted.
  const [cancelling, setCancelling] = useState(false)
  // No reply at all (e.g. a recording service that predates cancel and
  // silently ignores the message) must not leave the spinner up forever.
  const [cancelTimeoutError, setCancelTimeoutError] = useState<string | null>(null)
  useEffect(() => {
    if (cancelError) setCancelling(false)
  }, [cancelError])
  useEffect(() => {
    if (!cancelling || stage !== 'recording') return
    const timer = setTimeout(() => {
      setCancelling(false)
      setCancelTimeoutError("The recording service didn't respond. Try again.")
    }, CANCEL_REPLY_TIMEOUT_MS)
    return () => clearTimeout(timer)
  }, [cancelling, stage])

  const confirmCancel = () => {
    setCancelTimeoutError(null)
    setCancelling(sendCancel())
  }
  // RFB only ever inserts its canvas into the DOM once its own connection
  // reaches 'connected' — a stalled/failed handshake past the raw
  // WebSocket (security negotiation, ServerInit, etc.) otherwise leaves
  // this silently blank forever with no indication anywhere of why.
  const [vncError, setVncError] = useState<string | null>(null)

  // Cancel / Stop and Save stay hidden until the recording screen is
  // actually usable: the control socket is only accepted once the service
  // has fully started the session (display + Codegen), and RFB's `connect`
  // means the video is rendering. Latched — a later transient reconnect
  // doesn't hide them again (the "Reconnecting" indicator covers that).
  // A VNC error shows them regardless, so a video that never loads can't
  // strand the human without a way to cancel.
  const [vncConnected, setVncConnected] = useState(false)
  const handleVncConnect = useCallback(() => setVncConnected(true), [])
  const [screenReady, setScreenReady] = useState(false)
  useEffect(() => {
    if (vncConnected && connected) setScreenReady(true)
  }, [vncConnected, connected])
  const showControls = screenReady || vncError !== null

  // This window was opened via `window.open()` (RecordAndPlay.tsx's
  // `startRecording`), so `window.close()` is allowed here — the opener
  // tab already got its own `saved` broadcast independently and has moved
  // on to its toast+reset; this tab doesn't depend on that in any way, it
  // just closes itself once the human's had a moment to read the result.
  useEffect(() => {
    if (stage !== 'success' && stage !== 'cancelled') return
    const timer = setTimeout(() => window.close(), AUTO_CLOSE_DELAY_MS)
    return () => clearTimeout(timer)
  }, [stage])

  // Live recording: the video is the window, full-bleed — but our own
  // controls live in their own reserved strip *above* the video (normal
  // layout flow), never floated on top of it. A remote-desktop viewer
  // showing the real Chromium window + Inspector must never have any of
  // its own screen content covered by AITestGen chrome.
  if (stage === 'recording' || stage === 'saving') {
    return (
      <div style={{ position: 'fixed', inset: 0, display: 'flex', flexDirection: 'column', background: '#000' }}>
        <div
          style={{
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'space-between',
            gap: 12,
            padding: '8px 14px',
            background: '#1a1a1e',
            flex: 'none',
          }}
        >
          <div style={{ display: 'flex', alignItems: 'center', gap: 8, minWidth: 0 }}>
            <FontAwesomeIcon icon={faCircleDot} style={{ fontSize: 11, color: '#ff5d5d', flex: 'none' }} />
            <span style={{ fontSize: 12.5, fontWeight: 600, color: '#fff', flex: 'none' }}>Recording</span>
            {applicationName && (
              <span
                style={{
                  fontSize: 12,
                  color: 'rgba(255,255,255,0.6)',
                  overflow: 'hidden',
                  textOverflow: 'ellipsis',
                  whiteSpace: 'nowrap',
                }}
              >
                {applicationName}
              </span>
            )}
            {reconnecting && (
              <span style={{ fontSize: 12, color: 'rgba(255,255,255,0.75)', flex: 'none' }}>
                <LoadingDots label="Reconnecting" />
              </span>
            )}
            {stopWarning && (
              <span style={{ fontSize: 12, color: '#ffb84d', flex: 'none' }}>{stopWarning}</span>
            )}
          </div>
          {showControls ? (
            <div style={{ display: 'flex', alignItems: 'center', gap: 8, flex: 'none' }}>
              <button
                type="button"
                onClick={() => setConfirmingCancel(true)}
                disabled={stage === 'saving'}
                style={{
                  display: 'inline-flex',
                  alignItems: 'center',
                  height: 30,
                  padding: '0 14px',
                  borderRadius: 7,
                  background: 'transparent',
                  color: 'rgba(255,255,255,0.85)',
                  border: '1px solid rgba(255,255,255,0.3)',
                  fontSize: 12.5,
                  fontWeight: 600,
                  cursor: stage === 'saving' ? 'default' : 'pointer',
                  opacity: stage === 'saving' ? 0.5 : 1,
                }}
              >
                Cancel
              </button>
              <button
                type="button"
                onClick={sendStop}
                disabled={stage === 'saving'}
                style={{
                  display: 'inline-flex',
                  alignItems: 'center',
                  gap: 8,
                  height: 30,
                  padding: '0 14px',
                  borderRadius: 7,
                  background: '#d33',
                  color: 'white',
                  border: 'none',
                  fontSize: 12.5,
                  fontWeight: 600,
                  cursor: stage === 'saving' ? 'default' : 'pointer',
                  opacity: stage === 'saving' ? 0.7 : 1,
                  flex: 'none',
                }}
              >
                {stage === 'saving' ? <LoadingDots label="Saving" /> : 'Stop and Save'}
              </button>
            </div>
          ) : (
            <span style={{ fontSize: 12, color: 'rgba(255,255,255,0.75)', flex: 'none' }}>
              <LoadingDots label="Loading recording screen" />
            </span>
          )}
        </div>

        {confirmingCancel && stage === 'recording' && (
          <div
            role="dialog"
            aria-modal="true"
            aria-label="Discard recording"
            onClick={() => {
              if (!cancelling) setConfirmingCancel(false)
            }}
            style={{
              position: 'fixed',
              inset: 0,
              background: 'rgba(15,23,42,0.6)',
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
              padding: 24,
              zIndex: 100,
            }}
          >
            <div
              onClick={(e) => e.stopPropagation()}
              style={{ maxWidth: 420, width: '100%', padding: 24, background: 'var(--panel, #fff)', borderRadius: 14, boxShadow: 'var(--panel-shadow)' }}
            >
              <div style={{ display: 'flex', gap: 14, marginBottom: 18 }}>
                <span
                  aria-hidden="true"
                  style={{
                    display: 'inline-flex',
                    width: 40,
                    height: 40,
                    borderRadius: 1000,
                    background: 'color-mix(in srgb, var(--bad, #d33) 12%, transparent)',
                    color: 'var(--bad, #d33)',
                    alignItems: 'center',
                    justifyContent: 'center',
                    flexShrink: 0,
                  }}
                >
                  <FontAwesomeIcon icon={faTriangleExclamation} style={{ fontSize: 17 }} />
                </span>
                <div style={{ minWidth: 0 }}>
                  <div style={{ fontSize: 17, fontWeight: 700, marginBottom: 4, color: 'var(--fg, #1b1f24)' }}>
                    Discard this recording?
                  </div>
                  <p style={{ margin: 0, lineHeight: 1.5, fontSize: 13, color: 'var(--fg-3, #666)' }}>
                    Everything recorded so far will be thrown away. Nothing is saved to your test cases.
                  </p>
                  {(cancelError ?? cancelTimeoutError) && (
                    <p style={{ margin: '8px 0 0', lineHeight: 1.5, fontSize: 12.5, color: 'var(--bad, #d33)' }}>
                      {cancelError ?? cancelTimeoutError}
                    </p>
                  )}
                </div>
              </div>
              <div style={{ display: 'flex', justifyContent: 'flex-end', gap: 10 }}>
                <button
                  type="button"
                  disabled={cancelling}
                  onClick={() => setConfirmingCancel(false)}
                  style={{ padding: '9px 16px', borderRadius: 8, border: '1px solid var(--border-2, #ddd)', background: 'var(--panel, #fff)', color: 'var(--fg-2, #333)', fontWeight: 600, cursor: cancelling ? 'default' : 'pointer' }}
                >
                  Keep recording
                </button>
                <button
                  type="button"
                  disabled={cancelling}
                  onClick={confirmCancel}
                  style={{
                    display: 'inline-flex',
                    alignItems: 'center',
                    gap: 8,
                    padding: '9px 16px',
                    borderRadius: 8,
                    border: 'none',
                    background: 'var(--bad, #d33)',
                    color: '#FFFFFF',
                    fontWeight: 600,
                    cursor: cancelling ? 'default' : 'pointer',
                    opacity: cancelling ? 0.7 : 1,
                  }}
                >
                  {cancelling ? <LoadingDots label="Discarding" /> : 'Discard'}
                </button>
              </div>
            </div>
          </div>
        )}

        {authMode === 'logged_out' && (
          <div
            style={{
              padding: '6px 14px',
              fontSize: 11.5,
              color: '#ffd8a8',
              background: '#3a2600',
              flex: 'none',
            }}
          >
            Anything you type — including passwords — is recorded into the generated test.
          </div>
        )}

        <div style={{ position: 'relative', flex: 1, minHeight: 0 }}>
          <VncCanvas
            url={vncWsUrl}
            style={{ width: '100%', height: '100%' }}
            onError={setVncError}
            onConnect={handleVncConnect}
          />
          {vncError && (
            <div
              style={{
                position: 'absolute',
                inset: 0,
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'center',
                padding: 20,
                textAlign: 'center',
                fontSize: 12.5,
                color: '#fff',
                background: 'rgba(0,0,0,0.88)',
              }}
            >
              {vncError}
            </div>
          )}
        </div>
      </div>
    )
  }

  // Success/cancelled/error: no video to show at this point — the opener tab (still
  // open in Vantage) is the one with real "View in Suite"/"Record another"
  // actions, driven off its own independent control-socket broadcast of the
  // same saved/failed message. A normal centered card is fine here.
  return (
    <div
      style={{
        position: 'fixed',
        inset: 0,
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
        background: 'var(--bg, #f5f6f8)',
        padding: 20,
      }}
    >
      {stage === 'success' && saved && (
        <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 12, textAlign: 'center' }}>
          <div style={{ fontSize: 15, fontWeight: 600, color: 'var(--fg, #1b1f24)' }}>Recording saved</div>
          <div style={{ fontSize: 13, color: 'var(--fg-3, #666)' }}>
            Test case TC-{String(saved.testCaseNumber).padStart(3, '0')} was added to your test cases.
          </div>
          <div style={{ fontSize: 12, color: 'var(--fg-4, #888)' }}>This tab will close automatically.</div>
        </div>
      )}

      {stage === 'cancelled' && (
        <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 12, textAlign: 'center' }}>
          <div style={{ fontSize: 15, fontWeight: 600, color: 'var(--fg, #1b1f24)' }}>Recording cancelled</div>
          <div style={{ fontSize: 13, color: 'var(--fg-3, #666)' }}>Nothing was saved to your test cases.</div>
          <div style={{ fontSize: 12, color: 'var(--fg-4, #888)' }}>This tab will close automatically.</div>
        </div>
      )}

      {stage === 'error' && (
        <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 12, textAlign: 'center', maxWidth: 480 }}>
          <div style={{ fontSize: 15, fontWeight: 600, color: 'var(--bad, #d33)' }}>The recording could not be saved</div>
          {errorMessage && (
            <div
              style={{
                fontSize: 12.5,
                color: 'var(--fg-3, #666)',
                fontFamily: 'var(--font-mono)',
                whiteSpace: 'pre-wrap',
                background: 'var(--panel-2, #f0f0f0)',
                border: '1px solid var(--border-2, #ddd)',
                borderRadius: 8,
                padding: '10px 12px',
                maxHeight: 160,
                overflow: 'auto',
              }}
            >
              {errorMessage}
            </div>
          )}
          <div style={{ fontSize: 12, color: 'var(--fg-4, #888)' }}>You can close this tab and try again from Vantage.</div>
        </div>
      )}
    </div>
  )
}

// The recording worker's virtual display (apps/workers/recording/src/
// recording_worker/config.py's VIEWPORT_WIDTH/VIEWPORT_HEIGHT) — keep in
// sync with that file if it ever changes.
const REMOTE_DISPLAY_WIDTH = 1920
const REMOTE_DISPLAY_HEIGHT = 1080
const REMOTE_ASPECT_RATIO = REMOTE_DISPLAY_WIDTH / REMOTE_DISPLAY_HEIGHT

// The whole noVNC integration surface this feature needs: hand `RFB` an
// empty container div and the session's own `vnc_ws_url` (RFB-protocol
// only — never mixed with the separate `control` JSON channel) and it owns
// frame rendering plus mouse/keyboard input relay from here on.
//
// `RFB` only appends its canvas to `container` once the connection reaches
// 'connected' (confirmed in its own source, node_modules/@novnc/novnc/core/rfb.js)
// — a handshake failure past the raw WebSocket (security negotiation,
// ServerInit, etc.) otherwise leaves the container silently empty forever.
// `securityfailure`/`disconnect` are the two RFB events that catch that.
//
// `scaleViewport` fits the fixed 1920x1080 remote screen into whatever box
// it's given while preserving aspect ratio (confirmed in noVNC's own
// Display.autoscale — a single uniform scale ratio, the classic letterbox
// computation) — if that box's own aspect ratio doesn't already match
// 1920:1080, the leftover space renders as plain background inside the
// canvas itself. Rather than accept that, an outer wrapper here measures
// its own available space (ResizeObserver) and sizes an inner box to the
// largest rectangle that both fits within it *and* matches 1920:1080
// exactly — RFB's own resize observer (it watches its container directly)
// then picks up that size change and scales with zero leftover space.
function VncCanvas({
  url,
  style,
  onError,
  onConnect,
}: {
  url: string
  style?: React.CSSProperties
  onError: (message: string | null) => void
  // Must be stable — it's an effect dependency, and a new identity would
  // tear down and recreate the RFB connection.
  onConnect: () => void
}) {
  const outerRef = useRef<HTMLDivElement | null>(null)
  const containerRef = useRef<HTMLDivElement | null>(null)
  const [box, setBox] = useState({ width: 0, height: 0 })

  useEffect(() => {
    const outer = outerRef.current
    if (!outer) return
    function fit() {
      const { width: availableWidth, height: availableHeight } = outer!.getBoundingClientRect()
      let width = availableWidth
      let height = width / REMOTE_ASPECT_RATIO
      if (height > availableHeight) {
        height = availableHeight
        width = height * REMOTE_ASPECT_RATIO
      }
      setBox({ width, height })
    }
    fit()
    const observer = new ResizeObserver(fit)
    observer.observe(outer)
    return () => observer.disconnect()
  }, [])

  useEffect(() => {
    const container = containerRef.current
    if (!container) return
    onError(null)
    const rfb = new RFB(container, url)
    rfb.scaleViewport = true
    rfb.background = '#000000'

    function handleSecurityFailure(event: CustomEvent<{ status: number; reason?: string }>) {
      onError(
        `Security negotiation with the recording session failed${
          event.detail.reason ? `: ${event.detail.reason}` : ` (status ${event.detail.status})`
        }.`,
      )
    }
    function handleDisconnect(event: CustomEvent<{ clean: boolean }>) {
      if (!event.detail.clean) {
        onError('The connection to the recording browser closed unexpectedly.')
      }
    }
    function handleConnect() {
      onError(null)
      onConnect()
    }
    rfb.addEventListener('securityfailure', handleSecurityFailure as EventListener)
    rfb.addEventListener('disconnect', handleDisconnect as EventListener)
    rfb.addEventListener('connect', handleConnect)

    return () => {
      rfb.removeEventListener('securityfailure', handleSecurityFailure as EventListener)
      rfb.removeEventListener('disconnect', handleDisconnect as EventListener)
      rfb.removeEventListener('connect', handleConnect)
      rfb.disconnect()
    }
  }, [url, onError, onConnect])

  return (
    <div ref={outerRef} style={{ ...style, display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
      <div ref={containerRef} style={{ width: box.width || '100%', height: box.height || '100%' }} />
    </div>
  )
}
