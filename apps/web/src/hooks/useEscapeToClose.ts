import { useEffect } from 'react'

// Module-level, not per-hook-instance: two dialogs can be mounted at once
// (e.g. a row's delete-confirm popover opened while a code/artifacts modal
// is also up), and each hook call used to save/restore the *other's* raw
// overflow value independently — whichever closed last could stomp it back
// to 'hidden' with nothing left open to ever undo it, wedging scroll on
// every page until reload. A shared count only unlocks once nothing is
// holding the lock.
let lockCount = 0
let previousOverflow = ''

function lockScroll() {
  const scrollEl = document.getElementById('app-shell-scroll') ?? document.body
  if (lockCount === 0) previousOverflow = scrollEl.style.overflow
  lockCount++
  scrollEl.style.overflow = 'hidden'
}

function unlockScroll() {
  lockCount = Math.max(0, lockCount - 1)
  if (lockCount === 0) {
    const scrollEl = document.getElementById('app-shell-scroll') ?? document.body
    scrollEl.style.overflow = previousOverflow
  }
}

// Also locks page scroll while active — every caller of this hook is a
// full-viewport dialog/overlay, and without this the page behind it kept
// scrolling alongside the dialog's own scrollbar, which read as two
// competing scrollbars and let the dimmed background scroll into its own
// blank space below whatever content it had.
//
// `document.body` itself is never the scrolling element in this app —
// AppShell's `#app-shell-scroll` (the flex:1 main-content pane beside the
// fixed sidebar) is — so that's what actually needs locking; body is kept
// as a fallback for contexts without AppShell mounted (preview-entry.tsx,
// component tests).
export function useEscapeToClose(onClose: () => void, active: boolean = true) {
  useEffect(() => {
    if (!active) return
    function handleKeyDown(e: KeyboardEvent) {
      if (e.key === 'Escape') onClose()
    }
    document.addEventListener('keydown', handleKeyDown)
    lockScroll()
    return () => {
      document.removeEventListener('keydown', handleKeyDown)
      unlockScroll()
    }
  }, [onClose, active])
}
