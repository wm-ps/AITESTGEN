export function Pagination({
  page,
  totalPages,
  onPrev,
  onNext,
}: {
  page: number
  totalPages: number
  onPrev: () => void
  onNext: () => void
}) {
  if (totalPages <= 1) return null
  return (
    <div
      style={{
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'space-between',
        gap: 'var(--space-3)',
        padding: 'var(--space-4) var(--space-5)',
      }}
    >
      <button type="button" className="button-secondary" disabled={page <= 0} onClick={onPrev}>
        Prev
      </button>
      <span className="caption" style={{ fontSize: 12, whiteSpace: 'nowrap' }}>
        Page {page + 1} of {totalPages}
      </span>
      <button type="button" className="button-secondary" disabled={page >= totalPages - 1} onClick={onNext}>
        Next
      </button>
    </div>
  )
}
