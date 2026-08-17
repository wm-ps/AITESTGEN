import { Component, type ReactNode } from 'react'
import { SERVICE_ERROR_COPY, type ServiceErrorCode } from '../errorCodes'

// Generic full-page fallback for "backend unreachable" or "something in the
// tree threw" — the code tells you which pod to go look at without needing
// to read free-text error messages. Anywhere/any-time per request: mounted
// directly by App.tsx for a failed bootstrap fetch (API_UNAVAILABLE), and by
// the ErrorBoundary below for uncaught render errors anywhere in the tree
// (UNEXPECTED_ERROR).
export function ServiceError({
  code = 'UNEXPECTED_ERROR',
  onRetry,
}: {
  code?: ServiceErrorCode
  onRetry?: () => void
}) {
  const { title, message } = SERVICE_ERROR_COPY[code]
  return (
    <main
      style={{
        height: '100vh',
        display: 'flex',
        flexDirection: 'column',
        alignItems: 'center',
        justifyContent: 'center',
        gap: 'var(--space-7)',
        textAlign: 'center',
        padding: 'var(--space-9)',
        boxSizing: 'border-box',
      }}
    >
      <svg width={72} height={72} viewBox="0 0 24 24" fill="none" stroke="var(--ink-faint)" strokeWidth={1.5} strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
        <path d="M9.5 9.5 3 3M14.5 14.5 21 21" />
        <path d="M8 16H5a4 4 0 0 1-.5-7.97" />
        <path d="M9 9h6a4 4 0 0 1 3.96 4.55" />
        <path d="M12 12v.01" />
      </svg>
      <div>
        <h1 style={{ fontSize: 20, fontWeight: 700, color: 'var(--ink)', margin: '0 0 6px' }}>{title}</h1>
        <p style={{ fontSize: 14.5, color: 'var(--ink-muted)', margin: 0, maxWidth: 380 }}>{message}</p>
        <p style={{ fontSize: 11.5, color: 'var(--ink-faint)', fontFamily: 'var(--font-mono)', margin: '10px 0 0' }}>
          Error code: {code}
        </p>
      </div>
      <button
        type="button"
        className="button-primary"
        style={{ padding: '10px 20px', fontSize: 14.5 }}
        onClick={onRetry ?? (() => window.location.reload())}
      >
        Retry
      </button>
    </main>
  )
}

// Same codes, inline — for a failed action inside a screen that shouldn't be
// blown away wholesale (e.g. a "Generate" button failing while the rest of
// the review screen is still usable).
export function ServiceErrorNote({ code }: { code: ServiceErrorCode }) {
  const { message } = SERVICE_ERROR_COPY[code]
  return (
    <p className="caption" role="alert" style={{ color: 'var(--danger)' }}>
      {message} <span style={{ fontFamily: 'var(--font-mono)', fontSize: 11 }}>({code})</span>
    </p>
  )
}

export class ErrorBoundary extends Component<{ children: ReactNode }, { hasError: boolean }> {
  state = { hasError: false }

  static getDerivedStateFromError() {
    return { hasError: true }
  }

  render() {
    if (this.state.hasError) return <ServiceError code="UNEXPECTED_ERROR" />
    return this.props.children
  }
}
