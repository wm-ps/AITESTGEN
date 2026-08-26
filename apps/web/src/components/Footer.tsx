export function Footer() {
  return (
    <footer
      style={{
        padding: 'var(--space-5) var(--space-8)',
        textAlign: 'center',
        borderTop: '1px solid var(--border-hairline)',
        background: 'var(--canvas)',
      }}
    >
      <span className="caption" style={{ fontSize: 12 }}>
        © {new Date().getFullYear()} Vantage
      </span>
    </footer>
  )
}
