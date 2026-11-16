// A UI hint, never authentication: "this browser had a live session last
// time". It only decides what shows while the mount-time me() check is still
// in flight — the boot loader (hinted) or the prerendered public page (not).
// me() stays the source of truth; App.tsx sets the hint once a user is
// confirmed and clears it whenever the user resolves to signed out (logout,
// expiry, an invalid session). The session cookie itself is httpOnly, so the
// page can't read it to decide.

// index.html's inline head script reads the same key.
const KEY = 'vantage.signedIn'

export function hasSignedInHint(): boolean {
  try {
    return window.localStorage.getItem(KEY) === '1'
  } catch {
    return false
  }
}

export function setSignedInHint(signedIn: boolean) {
  try {
    if (signedIn) window.localStorage.setItem(KEY, '1')
    else window.localStorage.removeItem(KEY)
  } catch {
    // Storage blocked: the hint is only a nicety, so carry on without it.
  }
}
