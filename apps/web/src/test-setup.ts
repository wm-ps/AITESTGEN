import '@testing-library/jest-dom/vitest'
import { beforeEach } from 'vitest'
import * as React from 'react'

// recharts (and its react-smooth dep) reference the classic JSX pragma's
// global `React` at runtime instead of importing it — real browsers get
// this from the app's own bundle, jsdom doesn't, so any recharts render
// throws `ReferenceError: React is not defined` without this.
;(globalThis as unknown as { React: typeof React }).React = React

// jsdom has no ResizeObserver — recharts' ResponsiveContainer needs one to
// measure its parent, so without a stub any chart renders at zero size.
class StubResizeObserver {
  observe() {}
  unobserve() {}
  disconnect() {}
}
;(globalThis as unknown as { ResizeObserver: typeof StubResizeObserver }).ResizeObserver = StubResizeObserver

// jsdom starts each test with an empty <head> — vitest doesn't load
// index.html the way the real browser does. Seed the same static
// title/favicon <link> index.html defines so tests exercise the real
// starting DOM state.
beforeEach(() => {
  // Order matters: replacing head's innerHTML after setting title would wipe
  // out the <title> element the setter just created.
  document.head.innerHTML = '<link rel="icon" type="image/png" href="/favicon.png" />'
  document.title = 'Vantage'
})
