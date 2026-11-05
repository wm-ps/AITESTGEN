import { useRef } from 'react'
import { fireEvent, render, screen } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { AnchoredMenu } from './AnchoredMenu'

function Harness({ open, onClose }: { open: boolean; onClose: () => void }) {
  const ref = useRef<HTMLButtonElement>(null)
  return (
    <>
      <button ref={ref}>anchor</button>
      <AnchoredMenu anchorRef={ref} open={open} onClose={onClose}>
        <div role="menu">
          <button>Item</button>
        </div>
      </AnchoredMenu>
    </>
  )
}

// jsdom has no layout: fake the trigger rect and the menu's measured size.
function mockLayout(anchorBottom: number, menuHeight: number) {
  vi.spyOn(HTMLElement.prototype, 'getBoundingClientRect').mockImplementation(function (this: HTMLElement) {
    if (this.tagName === 'BUTTON' && this.textContent === 'anchor') {
      return { top: anchorBottom - 24, bottom: anchorBottom, left: 700, right: 724, width: 24, height: 24, x: 700, y: anchorBottom - 24, toJSON() {} }
    }
    return { top: 0, bottom: menuHeight, left: 0, right: 140, width: 140, height: menuHeight, x: 0, y: 0, toJSON() {} }
  })
}

afterEach(() => vi.restoreAllMocks())

describe('AnchoredMenu', () => {
  it('opens below the trigger when there is room', () => {
    window.innerHeight = 768
    mockLayout(100, 90)
    render(<Harness open onClose={() => {}} />)
    const panel = screen.getByRole('menu').parentElement!
    expect(panel.style.top).toBe('104px')
  })

  it('opens above the trigger when there is not enough room below', () => {
    window.innerHeight = 768
    mockLayout(740, 90)
    render(<Harness open onClose={() => {}} />)
    const panel = screen.getByRole('menu').parentElement!
    // anchor top (716) - gap (4) - menu height (90)
    expect(panel.style.top).toBe('622px')
  })

  it('closes on outside mousedown, Escape, scroll and resize, but not on inside click', () => {
    mockLayout(100, 90)
    const onClose = vi.fn()
    render(<Harness open onClose={onClose} />)

    fireEvent.mouseDown(screen.getByText('Item'))
    fireEvent.mouseDown(screen.getByText('anchor'))
    expect(onClose).not.toHaveBeenCalled()

    fireEvent.mouseDown(document.body)
    fireEvent.keyDown(document, { key: 'Escape' })
    fireEvent.scroll(document.body)
    fireEvent.resize(window)
    expect(onClose).toHaveBeenCalledTimes(4)
  })

  it('renders nothing when closed', () => {
    render(<Harness open={false} onClose={() => {}} />)
    expect(screen.queryByRole('menu')).not.toBeInTheDocument()
  })
})
