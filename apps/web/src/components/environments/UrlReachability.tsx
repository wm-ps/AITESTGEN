import type { UrlResult } from './environmentValidation'

// The URL check's result under the Deployed URL, as in application onboarding:
// "URL is reachable." in green, or why not in red.
export function UrlReachability({ result }: { result: UrlResult | null }) {
  if (!result) return null
  return <div style={{ fontSize: 12, marginTop: -8, color: result.ok ? 'var(--ok)' : 'var(--bad)' }}>{result.text}</div>
}
