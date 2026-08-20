export function Logo({ size = 34 }: { size?: number }) {
  return (
    <svg
      aria-hidden="true"
      width={size}
      height={size}
      viewBox="0 0 34 34"
      style={{ borderRadius: size <= 30 ? 'var(--radius-sm)' : 'var(--radius-md)', flexShrink: 0, display: 'block' }}
    >
      <defs>
        <linearGradient id="logo-shade" x1="0" y1="0" x2="1" y2="1">
          <stop offset="0%" stopColor="#000000" stopOpacity="0" />
          <stop offset="65%" stopColor="#000000" stopOpacity="0" />
          <stop offset="100%" stopColor="#000000" stopOpacity="0.22" />
        </linearGradient>
      </defs>
      <rect width="34" height="34" rx="10" fill="var(--accent)" />
      <rect width="34" height="34" rx="10" fill="url(#logo-shade)" />
      <circle cx="14" cy="14" r="7" fill="none" stroke="#ffffff" strokeWidth="2.4" />
      <line x1="19.2" y1="19.2" x2="26.5" y2="26.5" stroke="#ffffff" strokeWidth="3" strokeLinecap="round" />
      <path d="M10.5 14.5L13 17L18 10.5" fill="none" stroke="#ffffff" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  )
}
