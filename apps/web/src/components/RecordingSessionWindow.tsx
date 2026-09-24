import { useEffect, useRef, useState } from 'react'
import RFB from '@novnc/novnc'
import { faCircleDot } from '@fortawesome/free-solid-svg-icons'
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

// Long enough to actually read the test case number before the tab closes
// itself — only the success path auto-closes; an error state stays open so
// the human can read why and decide what to do (retry, or close manually).
const AUTO_CLOSE_DELAY_MS = 2500

export function RecordingSessionWindow({ vncWsUrl, controlWsUrl, authMode, applicationName }: RecordingPopupParams) {
  const { stage, reconnecting, errorMessage, saved, stopWarning, sendStop } = useRecordingControlSocket(controlWsUrl)
  // RFB only ever inserts its canvas into the DOM once its own connection
  // reaches 'connected' — a stalled/failed handshake past the raw
  // WebSocket (security negotiation, ServerInit, etc.) otherwise leaves
  // this silently blank forever with no indication anywhere of why.
  const [vncError, setVncError] = useState<string | null>(null)

  // This window was opened via `window.open()` (RecordAndPlay.tsx's
  // `startRecording`), so `window.close()` is allowed here — the opener
  // tab already got its own `saved` broadcast independently and has moved
  // on to its toast+reset; this tab doesn't depend on that in any way, it
  // just closes itself once the human's had a moment to read the result.
  useEffect(() => {
    if (stage !== 'success') return
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
          <VncCanvas url={vncWsUrl} style={{ width: '100%', height: '100%' }} onError={setVncError} />
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

  // Success/error: no video to show at this point — the opener tab (still
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
            Test case TC-{String(saved.testCaseNumber).padStart(3, '0')} was added to the test suite.
          </div>
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
}: {
  url: string
  style?: React.CSSProperties
  onError: (message: string | null) => void
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
  }, [url, onError])

  return (
    <div ref={outerRef} style={{ ...style, display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
      <div ref={containerRef} style={{ width: box.width || '100%', height: box.height || '100%' }} />
    </div>
  )
}
