import { useCallback, useEffect, useRef, useState } from 'react'

// Shared by the main "Record and play" tab and the popped-out recording
// window (RecordingSessionWindow.tsx) — both open their own independent
// `control` websocket against the same RecordingSession (the recording
// service's `SessionRuntime` tracks control sockets as a set and broadcasts
// to all of them, so two simultaneous listeners is an already-supported
// shape, not a workaround).

export type ControlStage = 'recording' | 'saving' | 'success' | 'error'

export type SavedResult = {
  journeyExternalId: string
  scenarioExternalId: string
  testCaseNumber: number
}

// A dropped control connection during an active recording retries for a
// while before giving up — the recording service itself tolerates a
// disconnect for its own grace window, so a transient network blip here
// should reconnect quietly rather than immediately erroring out.
const RECONNECT_RETRY_MS = 2000
const RECONNECT_MAX_ATTEMPTS = 30

// The control channel carries zero traffic between "recording started" and
// whenever the human eventually sends stop — observed live: something on
// this network path (VPN/proxy/firewall) silently kills idle WebSocket
// connections after ~2 minutes of no traffic (the exact same signature as
// this project's own Vite dev-server HMR socket dying every ~2 minutes with
// code 1006). A periodic real message is what defeats that class of
// middlebox, unlike a low-level WS protocol ping (not exposed to browser JS
// anyway). The server tolerates any message type it doesn't recognize
// (recordings_control's loop only acts on "stop"), so this needs no
// backend change.
const PING_INTERVAL_MS = 30_000

export function useRecordingControlSocket(controlWsUrl: string | null) {
  const [stage, setStage] = useState<ControlStage>('recording')
  const [reconnecting, setReconnecting] = useState(false)
  const [errorMessage, setErrorMessage] = useState<string | null>(null)
  const [saved, setSaved] = useState<SavedResult | null>(null)
  const [connected, setConnected] = useState(false)
  // Set when "Stop and Save" is clicked while the socket isn't actually
  // open — never silently swallow that click. Cleared on the next
  // reconnect or successful send.
  const [stopWarning, setStopWarning] = useState<string | null>(null)

  const socketRef = useRef<WebSocket | null>(null)
  const reconnectAttemptsRef = useRef(0)
  const reconnectTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null)
  const pingTimerRef = useRef<ReturnType<typeof setInterval> | null>(null)
  const stageRef = useRef<ControlStage>('recording')
  stageRef.current = stage

  useEffect(() => {
    if (!controlWsUrl) return

    setStage('recording')
    setReconnecting(false)
    setErrorMessage(null)
    setSaved(null)
    reconnectAttemptsRef.current = 0

    let cancelled = false

    function stopPing() {
      if (pingTimerRef.current) {
        clearInterval(pingTimerRef.current)
        pingTimerRef.current = null
      }
    }

    function connect() {
      const socket = new WebSocket(controlWsUrl!)
      socketRef.current = socket

      // Every handler below guards on `socketRef.current === socket` before
      // touching shared state. React 18 StrictMode double-invokes this
      // effect (mount -> cleanup -> mount), so a throwaway first socket is
      // created and closed practically immediately — but its `close` event
      // is still async and can arrive *after* the real, surviving socket
      // has already replaced it in `socketRef`. Without this guard, that
      // stale socket's belated `onclose` unconditionally nulled out
      // `socketRef.current`, clobbering a perfectly good, already-open
      // connection — `sendStop()` would then see `null` and report "not
      // connected" even though the real connection was fine the whole
      // time (observed live: no server-side disconnect logged at all for
      // the session in question).
      socket.onopen = () => {
        if (socketRef.current !== socket) return
        reconnectAttemptsRef.current = 0
        setReconnecting(false)
        setConnected(true)
        setStopWarning(null)
        stopPing()
        pingTimerRef.current = setInterval(() => {
          socketRef.current?.send(JSON.stringify({ type: 'ping' }))
        }, PING_INTERVAL_MS)
      }

      socket.onmessage = (event) => {
        if (socketRef.current !== socket) return
        let message: Record<string, unknown>
        try {
          message = JSON.parse(event.data)
        } catch {
          return
        }
        if (message.type === 'status' && message.state === 'saving') {
          setStage('saving')
        } else if (message.type === 'saved') {
          setSaved({
            journeyExternalId: String(message.journey_external_id),
            scenarioExternalId: String(message.scenario_external_id),
            testCaseNumber: Number(message.test_case_number),
          })
          setStage('success')
        } else if (message.type === 'failed') {
          setErrorMessage(typeof message.error === 'string' ? message.error : 'The recording could not be saved.')
          setStage('error')
        }
      }

      socket.onclose = () => {
        const isCurrent = socketRef.current === socket
        if (isCurrent) {
          socketRef.current = null
          setConnected(false)
          stopPing()
        }
        if (cancelled || !isCurrent) return
        // A finished session (success/error) already moved off 'recording'/
        // 'saving' — only a still-in-progress session's unexpected drop
        // should retry.
        if (stageRef.current !== 'recording' && stageRef.current !== 'saving') return
        if (reconnectAttemptsRef.current >= RECONNECT_MAX_ATTEMPTS) {
          setErrorMessage('Lost connection to the recording session.')
          setStage('error')
          return
        }
        reconnectAttemptsRef.current += 1
        setReconnecting(true)
        reconnectTimerRef.current = setTimeout(connect, RECONNECT_RETRY_MS)
      }
    }

    connect()

    return () => {
      cancelled = true
      if (reconnectTimerRef.current) clearTimeout(reconnectTimerRef.current)
      stopPing()
      socketRef.current?.close()
      socketRef.current = null
    }
  }, [controlWsUrl])

  const sendStop = useCallback(() => {
    const socket = socketRef.current
    if (!socket || socket.readyState !== WebSocket.OPEN) {
      setStopWarning('Not connected right now — reconnecting. Try Stop and Save again in a moment.')
      return
    }
    setStopWarning(null)
    socket.send(JSON.stringify({ type: 'stop' }))
  }, [])

  return { stage, reconnecting, errorMessage, saved, connected, stopWarning, sendStop }
}
