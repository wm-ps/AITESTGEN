import { useEffect, useLayoutEffect, useRef, useState, type ReactNode, type RefObject } from 'react'
import { createPortal } from 'react-dom'

const GAP = 4
const EDGE = 8

interface AnchoredMenuProps {
  /** The trigger button the menu hangs off. */
  anchorRef: RefObject<HTMLElement | null>
  open: boolean
  onClose: () => void
  /** The menu panel (border, shadow, items) — styled by the caller, positioned here. */
  children: ReactNode
}

/**
 * Row/card menu popover. Portaled to <body> so table `overflow: hidden`
 * can't clip it; right-aligned to the trigger, opens below when it fits and
 * above otherwise. Closes on outside click, Escape, scroll and resize.
 */
export function AnchoredMenu({ anchorRef, open, onClose, children }: AnchoredMenuProps) {
  const menuRef = useRef<HTMLDivElement>(null)
  const [pos, setPos] = useState<{ top: number; left: number } | null>(null)

  useLayoutEffect(() => {
    const anchor = anchorRef.current
    const menu = menuRef.current
    if (!open || !anchor || !menu) {
      setPos(null)
      return
    }
    const rect = anchor.getBoundingClientRect()
    const { width, height } = menu.getBoundingClientRect()
    const below = window.innerHeight - rect.bottom - GAP - EDGE
    const above = rect.top - GAP - EDGE
    const openAbove = height > below && above > below
    const top = openAbove ? Math.max(EDGE, rect.top - GAP - height) : rect.bottom + GAP
    const left = Math.min(Math.max(EDGE, rect.right - width), window.innerWidth - width - EDGE)
    setPos({ top, left })
  }, [open, anchorRef])

  useEffect(() => {
    if (!open) return
    const onMouseDown = (e: MouseEvent) => {
      const target = e.target as Node
      if (menuRef.current?.contains(target) || anchorRef.current?.contains(target)) return
      onClose()
    }
    const onKeyDown = (e: KeyboardEvent) => {
      if (e.key === 'Escape') onClose()
    }
    const onScroll = (e: Event) => {
      if (menuRef.current?.contains(e.target as Node)) return
      onClose()
    }
    document.addEventListener('mousedown', onMouseDown)
    document.addEventListener('keydown', onKeyDown)
    window.addEventListener('scroll', onScroll, true)
    window.addEventListener('resize', onClose)
    return () => {
      document.removeEventListener('mousedown', onMouseDown)
      document.removeEventListener('keydown', onKeyDown)
      window.removeEventListener('scroll', onScroll, true)
      window.removeEventListener('resize', onClose)
    }
  }, [open, onClose, anchorRef])

  if (!open) return null
  return createPortal(
    <div
      ref={menuRef}
      style={{
        position: 'fixed',
        top: pos?.top ?? 0,
        left: pos?.left ?? 0,
        width: 'max-content',
        zIndex: 100,
        // Measured off-screen-invisible first, then placed — avoids a flash at 0,0.
        visibility: pos ? 'visible' : 'hidden',
      }}
    >
      {children}
    </div>,
    document.body,
  )
}
