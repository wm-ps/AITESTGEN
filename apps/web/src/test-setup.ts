import { beforeEach } from 'vitest'

// jsdom starts each test with an empty <head> — vitest doesn't load
// index.html the way the real browser does. Seed the same static
// title/favicon <link> index.html defines so tests exercise the real
// starting DOM state.
beforeEach(() => {
  // Order matters: replacing head's innerHTML after setting title would wipe
  // out the <title> element the setter just created.
  document.head.innerHTML = '<link rel="icon" type="image/svg+xml" href="/favicon.svg" />'
  document.title = 'AITestGen'
})
