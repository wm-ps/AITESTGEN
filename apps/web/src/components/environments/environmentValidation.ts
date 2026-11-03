import { useEffect, useState } from 'react'
import { ApiError, DOMAIN_NOT_APPROVED_CODE, DOMAIN_NOT_APPROVED_MESSAGE, api } from '../../api'
import { checkCredentials } from '../credentialCheck'

export const INVALID_CREDENTIALS_MESSAGE =
  'The username or password is incorrect for this environment. Enter valid credentials and try again.'
export const UNCERTAIN_CREDENTIALS_MESSAGE = "We couldn't confirm these credentials. Try again."
const UNREACHABLE_MESSAGE = "This URL didn't respond. Confirm the environment is deployed and reachable, then try again."

// Debounced "is this URL's domain on the admin's approved list" — the same
// live check the Add application form runs. A failed check leaves it false:
// the API enforces the same rule on save, so a flaky check never blocks the
// dialog.
export function useDomainBlocked(url: string, enabled: boolean): boolean {
  const [blocked, setBlocked] = useState(false)
  useEffect(() => {
    if (!enabled || !url.trim()) {
      setBlocked(false)
      return
    }
    let stale = false
    const timeout = setTimeout(() => {
      api
        .checkDomain(url)
        .then((result) => !stale && setBlocked(!result.allowed))
        .catch(() => !stale && setBlocked(false))
    }, 400)
    return () => {
      stale = true
      clearTimeout(timeout)
    }
  }, [url, enabled])
  return blocked
}

export type ValidationProgress = 'Checking URL' | 'Validating credentials'

// What the URL check found, shown under the Deployed URL field.
export type UrlResult = { ok: boolean; text: string }

// What has to hold before an environment is saved, in the order onboarding
// runs it: the application is reachable at the environment's own URL, then a
// real browser login with the entered username and password succeeds at the
// environment's own login URL. Returns the message to show, or null when
// everything passed. Nothing here saves anything.
export async function validateEnvironment({
  url,
  loginUrl,
  username,
  password,
  checkUrl,
  checkLogin,
  onProgress,
  onUrlResult,
  isCancelled,
}: {
  url: string
  loginUrl?: string
  username: string
  password: string
  checkUrl: boolean
  checkLogin: boolean
  onProgress: (step: ValidationProgress) => void
  onUrlResult?: (result: UrlResult) => void
  isCancelled: () => boolean
}): Promise<string | null> {
  if (checkUrl) {
    onProgress('Checking URL')
    try {
      const result = await api.testConnection(url)
      if (!result.reachable) {
        const text = result.detail ?? UNREACHABLE_MESSAGE
        onUrlResult?.({ ok: false, text })
        return text
      }
      onUrlResult?.({ ok: true, text: 'URL is reachable.' })
    } catch (err) {
      const text =
        err instanceof ApiError && err.message === DOMAIN_NOT_APPROVED_CODE
          ? DOMAIN_NOT_APPROVED_MESSAGE
          : err instanceof ApiError
            ? err.message
            : 'Could not reach the server to test this URL.'
      onUrlResult?.({ ok: false, text })
      return text
    }
    if (isCancelled()) return null
  }
  if (checkLogin) {
    onProgress('Validating credentials')
    const verdict = await checkCredentials({ url, login_url: loginUrl || undefined, username, password }, isCancelled)
    if (isCancelled()) return null
    if (verdict === 'invalid') return INVALID_CREDENTIALS_MESSAGE
    if (verdict === 'uncertain') return UNCERTAIN_CREDENTIALS_MESSAGE
  }
  return null
}
