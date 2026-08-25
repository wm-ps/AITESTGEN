// Shared bottom-right notice — was two copy-pasted solid-black pills (App.tsx's
// errorToast, Workspace.tsx's runToast), the generic default look of an
// unstyled toast library rather than this app's own card/border/token system.
const TOAST_COLORS = {
  error: { accent: 'var(--danger)', wash: 'var(--danger-wash)' },
  info: { accent: 'var(--accent)', wash: 'var(--accent-wash)' },
} as const

function ToastGlyph({ kind }: { kind: keyof typeof TOAST_COLORS }) {
  return (
    <svg width={13} height={13} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2.4} strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
      <circle cx={12} cy={12} r={9.5} />
      {kind === 'error' ? (
        <>
          <line x1={12} y1={7.5} x2={12} y2={13} />
          <circle cx={12} cy={16.5} r={0.6} fill="currentColor" stroke="none" />
        </>
      ) : (
        <>
          <circle cx={12} cy={7.5} r={0.6} fill="currentColor" stroke="none" />
          <line x1={12} y1={10.5} x2={12} y2={16} />
        </>
      )}
    </svg>
  )
}

export function Toast({
  message,
  kind = 'error',
  onDismiss,
}: {
  message: string
  kind?: keyof typeof TOAST_COLORS
  onDismiss?: () => void
}) {
  const colors = TOAST_COLORS[kind]
  return (
    <div
      role="status"
      className="card-panel"
      style={{
        position: 'fixed',
        right: 'var(--space-9)',
        bottom: 'var(--space-9)',
        display: 'flex',
        alignItems: 'flex-start',
        gap: 10,
        padding: '13px 14px 13px 15px',
        boxShadow: '0 10px 24px -6px rgba(15,23,42,0.16), 0 2px 6px rgba(15,23,42,0.06)',
        fontSize: 13.5,
        lineHeight: 1.4,
        color: 'var(--ink)',
        maxWidth: 360,
        zIndex: 100,
        animation: 'aitg-fade-up 0.25s ease-out both',
      }}
    >
      <span
        aria-hidden="true"
        style={{
          width: 20,
          height: 20,
          marginTop: 1,
          borderRadius: 'var(--radius-full)',
          background: colors.wash,
          color: colors.accent,
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
          flexShrink: 0,
        }}
      >
        <ToastGlyph kind={kind} />
      </span>
      <span style={{ paddingTop: 1 }}>{message}</span>
      {onDismiss && (
        <button
          type="button"
          onClick={onDismiss}
          aria-label="Dismiss"
          style={{
            marginLeft: 'auto',
            background: 'none',
            border: 'none',
            cursor: 'pointer',
            color: 'var(--ink-faint)',
            fontSize: 16,
            lineHeight: 1,
            padding: 2,
            flexShrink: 0,
          }}
        >
          ×
        </button>
      )}
    </div>
  )
}
