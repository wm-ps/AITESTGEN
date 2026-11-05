import type { CSSProperties } from 'react'

// The one dialog look (New suite / Select test cases): plain panel, title +
// plain X, tinted footer bar with text-only Cancel + primary. Every dialog
// shell reuses these so they stay identical.
export const modalOverlay: CSSProperties = {
  position: 'fixed',
  inset: 0,
  background: 'rgba(15,23,42,0.35)',
  display: 'flex',
  alignItems: 'center',
  justifyContent: 'center',
  padding: 16,
  zIndex: 50,
}

export const modalPanel: CSSProperties = {
  background: 'var(--panel)',
  border: '1px solid var(--border-2)',
  borderRadius: 16,
  boxShadow: '0 30px 80px rgba(8,12,20,0.34), var(--panel-shadow)',
  width: '100%',
  maxHeight: '86vh',
  display: 'flex',
  flexDirection: 'column',
  overflow: 'hidden',
  boxSizing: 'border-box',
}

export const modalHeader: CSSProperties = {
  display: 'flex',
  alignItems: 'flex-start',
  justifyContent: 'space-between',
  gap: 12,
  padding: '20px 28px 16px',
}

export const modalTitle: CSSProperties = { fontSize: 17, fontWeight: 600, color: 'var(--fg)', margin: 0 }

export const modalCloseButton: CSSProperties = {
  background: 'none',
  border: 'none',
  cursor: 'pointer',
  color: 'var(--fg-3)',
  padding: 4,
}

export const modalFooter: CSSProperties = {
  display: 'flex',
  alignItems: 'center',
  justifyContent: 'flex-end',
  gap: 10,
  padding: '16px 28px',
  background: 'var(--bg-2)',
  borderTop: '1px solid var(--line)',
}

export const modalButton: CSSProperties = { padding: '10px 22px', fontSize: 14 }
