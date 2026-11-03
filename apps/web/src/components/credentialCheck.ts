import { api } from '../api'

// The login check runs in a real browser on the discovery worker and is
// polled, like Regenerate/Auto-fill. The cap sits just above the worker's
// own worst-case budget (credential_check.py) so a hung check ends as
// "couldn't confirm" instead of spinning forever.
const CREDENTIAL_POLL_MS = 1000
const CREDENTIAL_POLL_MAX_ATTEMPTS = 150

// Anything that isn't a proved `valid` / `invalid` (request error, worker
// unavailable, timeout) collapses to `uncertain` — nothing is saved on an
// unproven login, and the user is just asked to try again. `isCancelled` lets
// a closed dialog stop polling (the verdict is then discarded by the caller).
export async function checkCredentials(
  payload: {
    url: string
    login_url?: string
    username: string
    password: string
  },
  isCancelled: () => boolean = () => false,
): Promise<'valid' | 'invalid' | 'uncertain'> {
  try {
    const { check_id } = await api.startCredentialCheck(payload)
    for (let attempt = 0; attempt < CREDENTIAL_POLL_MAX_ATTEMPTS; attempt++) {
      if (isCancelled()) return 'uncertain'
      const result = await api.getCredentialCheck(check_id)
      if (result.status !== 'running') return result.status
      await new Promise((resolve) => setTimeout(resolve, CREDENTIAL_POLL_MS))
    }
  } catch {
    // fall through to uncertain
  }
  return 'uncertain'
}
